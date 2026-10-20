import io
import json
import re
import time
from pathlib import Path

import fitz
import yaml

from papertrail.audit import _hash
from papertrail.s1_index import search
from papertrail.web import create_app
from papertrail.workspace import library_documents, list_uploads


def _pdf(title: str, paragraphs: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 55), title, fontsize=16)
    y = 95
    for paragraph in paragraphs:
        page.insert_text((40, y), paragraph, fontsize=10)
        y += 28
    doc.set_metadata({"title": title})
    content = doc.tobytes()
    doc.close()
    return content


def _csrf(response) -> str:
    match = re.search(rb'name="_csrf" value="([^"]+)"', response.data)
    assert match
    return match.group(1).decode()


def _wait_for_job(client, response) -> dict:
    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                      response.get_data(as_text=True))
    assert match
    for _ in range(100):
        job_response = client.get(f"/jobs/{match.group(1)}")
        job = job_response.get_json()
        if job["state"] in {"succeeded", "succeeded_with_issues", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError("索引任务未及时结束")


def test_local_web_learning_loop_upload_qa_notes_comparison_report_and_delete(tmp_path):
    db = tmp_path / "workspace.sqlite3"
    uploads = tmp_path / "uploads"
    app = create_app(db, uploads)
    app.config.update(TESTING=True)
    client = app.test_client()

    page = client.get("/")
    assert page.status_code == 200
    assert b"PaperTrail" in page.data
    token = _csrf(page)
    rejected = client.post("/notes", data={"concept": "x", "body": "y"})
    assert rejected.status_code == 400

    a_bytes = _pdf("CTGAN Categorical Noise A", [
        "CTGAN evaluates mixed continuous and discrete columns with reliable likelihood and utility measurements.",
        "This method uses multinomial noise for categorical features and Gaussian noise for continuous variables.",
    ])
    b_bytes = _pdf("CTGAN Categorical Noise B", [
        "This approach avoids multinomial noise for categorical features and uses continuous feature values.",
    ])
    for name, payload in (("paper-a.pdf", a_bytes), ("paper-b.pdf", b_bytes)):
        response = client.post("/uploads", data={"_csrf": token,
            "pdf": (io.BytesIO(payload), name)}, content_type="multipart/form-data", follow_redirects=True)
        assert response.status_code == 200
        assert "后台索引任务已排队" in response.get_data(as_text=True)
        assert _wait_for_job(client, response)["state"] == "succeeded"
        token = _csrf(response)
    assert len(list_uploads(db)) == 2

    response = client.post("/ask", data={"_csrf": token, "question": "What does CTGAN evaluate?"},
                           follow_redirects=True)
    assert response.status_code == 200
    assert "PDF 第 1 页" in response.get_data(as_text=True)
    token = _csrf(response)

    response = client.post("/notes", data={"_csrf": token, "concept": "私人概念",
        "body": "personal-private-marker should never enter paper retrieval."}, follow_redirects=True)
    assert response.status_code == 200 and "私人概念".encode() in response.data
    assert search(db, "personal-private-marker", source_type="original_pdf") == []
    token = _csrf(response)

    response = client.post("/compare", data={"_csrf": token, "topic": "categorical noise",
        "claim": "uses multinomial noise for categorical features"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"unclassified" in response.data
    token = _csrf(response)
    report_response = client.get("/reports/study.json")
    report = json.loads(report_response.data)
    assert report["progress"]["documents"] == 2
    assert report["progress"]["personal_notes"] == 1
    assert report["question_turns"] and report["comparisons"]
    assert "personal-private-marker" in json.dumps(report["personal_notes"], ensure_ascii=False)
    assert "E:\\" not in report_response.get_data(as_text=True)

    upload = list_uploads(db)[0]
    path = upload["stored_path"]
    response = client.post(f"/uploads/{upload['upload_id']}/delete", data={"_csrf": token}, follow_redirects=True)
    assert response.status_code == 200
    assert len(list_uploads(db)) == 1
    assert not Path(path).exists()


def test_web_can_index_explicit_authorized_selection(tmp_path):
    root = tmp_path / "authorized"
    root.mkdir()
    source = root / "configured.pdf"
    source.write_bytes(_pdf("Configured Research Paper", [
        "A configured paper provides enough text to establish an indexable native PDF source."
    ]))
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "approved", "path": str(root)}]}), encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({"root_id": "approved", "file_name": source.name,
        "relative_path": source.name, "sha256": _hash(source), "kind": "pdf",
        "source_type": "original_pdf"}) + "\n", encoding="utf-8")
    app = create_app(tmp_path / "workspace.sqlite3", tmp_path / "uploads", config, selection)
    app.config.update(TESTING=True)
    client = app.test_client()
    page = client.get("/")
    response = client.post("/index-selected", data={"_csrf": _csrf(page)}, follow_redirects=True)
    assert response.status_code == 200
    assert _wait_for_job(client, response)["state"] == "succeeded"
    response = client.get("/")
    assert b"Configured Research Paper" in response.data
    response = client.post("/uploads", data={"_csrf": _csrf(response),
        "pdf": (io.BytesIO(source.read_bytes()), "duplicate.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    assert len(library_documents(tmp_path / "workspace.sqlite3")) == 1
    duplicate = list_uploads(tmp_path / "workspace.sqlite3")[0]
    response = client.post(f"/uploads/{duplicate['upload_id']}/delete",
                           data={"_csrf": _csrf(response)}, follow_redirects=True)
    assert response.status_code == 200
    assert len(library_documents(tmp_path / "workspace.sqlite3")) == 1
    assert search(tmp_path / "workspace.sqlite3", "configured paper", source_type="original_pdf")
