import hashlib
import json
from pathlib import Path

import fitz
import numpy as np
import pytest
import yaml

from papertrail.access import (Principal, assign_version_to_collection, authorized_version_ids,
                               create_collection, document_metadata, read_evidence, search_papers)
from papertrail.retrieval import vector_search
from papertrail.semantic import bge_search
from papertrail.mcp_server import _call, _resource_list, handle
from papertrail.qa import _validate_quote, ask
from papertrail.retrieval import retrieve
from papertrail.s1_index import index_selection, open_database, search
from papertrail.web import create_app


def _write_pdf(path: Path, title: str, text: str) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 50), title, fontsize=16)
    page.insert_textbox(fitz.Rect(40, 80, 550, 740), text, fontsize=9)
    doc.save(path)
    doc.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_docs(tmp_path: Path, docs: list[tuple[str, str]]) -> tuple[Path, Path, list[dict]]:
    root = tmp_path / "papers"
    root.mkdir()
    rows = []
    for filename, text in docs:
        digest = _write_pdf(root / filename, filename, text)
        rows.append({"root_id": "fixture", "file_name": filename, "relative_path": filename,
                     "sha256": digest, "kind": "pdf", "source_type": "original_pdf"})
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "fixture", "path": str(root)}]}),
                      encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    database = tmp_path / "library.sqlite3"
    assert index_selection(database, config, selection)["added"] == len(rows)
    return database, root, rows


def test_acl_filters_before_fts_limit_and_web_search(tmp_path):
    strong = " ".join(["workspacecandidate evidence marker."] * 35)
    database, _root, rows = _index_docs(tmp_path, [
        *((f"foreign-{index}.pdf", strong) for index in range(5)),
        ("owned.pdf", "workspacecandidate evidence marker. "
         "A local-only source remains available after workspace filtering. " * 12),
    ])
    create_collection(database, "workspace-b", "workspace-b-user")
    conn = open_database(database)
    try:
        foreign_versions = conn.execute(
            "SELECT version_id,sha256 FROM paper_versions WHERE file_name LIKE 'foreign-%'"
        ).fetchall()
    finally:
        conn.close()
    for version in foreign_versions:
        assign_version_to_collection(database, version["version_id"], "workspace-b")
    owned_sha = next(row["sha256"] for row in rows if row["file_name"] == "owned.pdf")

    local_rows = search(database, "workspacecandidate", limit=1, source_type="original_pdf",
                        principal_id="local-dev")
    assert [row["sha256"] for row in local_rows] == [owned_sha]
    foreign_rows = search(database, "workspacecandidate", limit=1, source_type="original_pdf",
                           principal_id="workspace-b-user")
    assert foreign_rows and foreign_rows[0]["rank_score"] > local_rows[0]["rank_score"]
    assert search(database, "workspacecandidate", limit=1, source_type="original_pdf",
                  principal_id="no-access") == []

    local_client = create_app(database, principal_provider=lambda: Principal("local-dev")).test_client()
    denied_client = create_app(database, principal_provider=lambda: Principal("no-access")).test_client()
    local_response = local_client.get("/api/search?q=workspacecandidate&limit=1")
    denied_response = denied_client.get("/api/search?q=workspacecandidate&limit=1")
    assert local_response.status_code == 200
    assert [row["sha256"] for row in local_response.json["results"]] == [owned_sha]
    assert denied_response.status_code == 200 and denied_response.json["results"] == []


def test_vector_candidates_are_filtered_before_scoring_and_top_k(tmp_path, monkeypatch):
    foreign_text = " ".join(["vectorworkspace marker foreign candidate."] * 20)
    database, _root, rows = _index_docs(tmp_path, [
        ("foreign.pdf", foreign_text),
        ("owned.pdf", "vectorworkspace marker owned candidate with enough text for indexing. " * 12),
    ])
    create_collection(database, "workspace-b", "workspace-b-user")
    conn = open_database(database)
    try:
        versions = {row["sha256"]: row["version_id"] for row in conn.execute(
            "SELECT version_id,sha256 FROM paper_versions")}
    finally:
        conn.close()
    assign_version_to_collection(database, versions[rows[0]["sha256"]], "workspace-b")

    def vector_row(source: dict) -> dict:
        return {"version_id": versions[source["sha256"]], "paper_id": "paper",
                "sha256": source["sha256"], "source_type": "original_pdf", "title": source["file_name"],
                "section_title": "Results", "page_number": 1,
                "absolute_path": str((_root / source["file_name"]).resolve()),
                "parse_status": "parsed", "text_origin": "native_text", "body": "candidate",
                "chunk_id": source["file_name"]}

    foreign_vector_row = vector_row(rows[0])
    owned_vector_row = vector_row(rows[1])
    bundle = {"rows": [foreign_vector_row, owned_vector_row],
              "vectors": np.asarray([[1.0, 0.0], [0.8, 0.6]], dtype=np.float32),
              "vectorizer": type("Vectorizer", (), {"transform": lambda _self, _query: np.asarray([[1.0, 0.0]])})(),
              "reducer": type("Reducer", (), {"transform": lambda _self, value: value})()}

    def normalize(values):
        return values / np.linalg.norm(values, axis=1, keepdims=True)

    import papertrail.retrieval as retrieval
    monkeypatch.setattr(retrieval, "_vector_dependencies", lambda: (None, np, None, None, normalize))
    monkeypatch.setattr(retrieval, "_load_index", lambda _database, _artifact: bundle)

    local_result = vector_search(database, "vectorworkspace", limit=1, principal_id="local-dev")
    assert [row["sha256"] for row in local_result] == [rows[1]["sha256"]]
    assert vector_search(database, "vectorworkspace", limit=1, principal_id="no-access") == []


def test_bge_candidates_are_filtered_before_scoring_and_top_k(tmp_path, monkeypatch):
    database, root, rows = _index_docs(tmp_path, [
        ("foreign.pdf", "bgeworkspace foreign semantic candidate."),
        ("owned.pdf", "bgeworkspace owned semantic candidate."),
    ])
    create_collection(database, "workspace-b", "workspace-b-user")
    conn = open_database(database)
    try:
        versions = {row["sha256"]: row["version_id"] for row in conn.execute(
            "SELECT version_id,sha256 FROM paper_versions")}
    finally:
        conn.close()
    assign_version_to_collection(database, versions[rows[0]["sha256"]], "workspace-b")

    def bge_row(source: dict) -> dict:
        return {"version_id": versions[source["sha256"]], "paper_id": "paper",
                "sha256": source["sha256"], "source_type": "original_pdf", "title": source["file_name"],
                "section_title": "Results", "page_number": 1,
                "absolute_path": str((root / source["file_name"]).resolve()),
                "parse_status": "parsed", "text_origin": "native_text", "body": "candidate",
                "chunk_id": source["file_name"]}

    bundle = {"rows": [bge_row(rows[0]), bge_row(rows[1])],
              "vectors": np.asarray([[1.0, 0.0], [0.8, 0.6]], dtype=np.float32)}
    import papertrail.semantic as semantic
    monkeypatch.setattr(semantic, "_load", lambda _database, _artifact: bundle)
    monkeypatch.setattr(semantic, "_encode", lambda _texts: np.asarray([[1.0, 0.0]], dtype=np.float32))

    local_result = bge_search(database, "bgeworkspace", limit=1, principal_id="local-dev")
    assert [row["sha256"] for row in local_result] == [rows[1]["sha256"]]
    assert bge_search(database, "bgeworkspace", limit=1, principal_id="no-access") == []


def test_direct_reads_and_mcp_tools_resources_share_collection_acl(tmp_path):
    database, _root, rows = _index_docs(tmp_path, [
        ("local.pdf", "directacl local-only synthetic evidence."),
        ("workspace.pdf", "directacl workspace-only synthetic evidence."),
    ])
    create_collection(database, "workspace-b", "workspace-b-user")
    conn = open_database(database)
    try:
        versions = {row["sha256"]: row["version_id"] for row in conn.execute(
            "SELECT version_id,sha256 FROM paper_versions")}
    finally:
        conn.close()
    assign_version_to_collection(database, versions[rows[1]["sha256"]], "workspace-b")
    local = Principal("local-dev")
    workspace = Principal("workspace-b-user")
    local_sha, workspace_sha = rows[0]["sha256"], rows[1]["sha256"]

    assert "local-only" in read_evidence(database, local_sha, 1, local)["text"]
    assert "workspace-only" in read_evidence(database, workspace_sha, 1, workspace)["text"]
    assert document_metadata(database, workspace_sha, workspace)["sha256"] == workspace_sha
    with pytest.raises(ValueError, match="original paper not found"):
        read_evidence(database, workspace_sha, 1, local)
    with pytest.raises(ValueError, match="original paper not found"):
        read_evidence(database, local_sha, 1, workspace)
    with pytest.raises(ValueError, match="original paper not found"):
        document_metadata(database, local_sha, workspace)

    workspace_tool = _call(database, "get_evidence",
                            {"sha256": workspace_sha, "page": 1}, workspace)
    assert "workspace-only" in workspace_tool["structuredContent"]["text"]
    assert {row["uri"] for row in _resource_list(database, workspace)} == {
        f"papertrail://documents/{workspace_sha}"}
    allowed_uri = f"papertrail://evidence/{workspace_sha}/1"
    allowed_read = handle(database, {"jsonrpc": "2.0", "id": 1,
                                     "method": "resources/read", "params": {"uri": allowed_uri}},
                          workspace)
    assert "workspace-only" in allowed_read["result"]["contents"][0]["text"]
    for uri in (f"papertrail://documents/{local_sha}",
                f"papertrail://evidence/{local_sha}/1"):
        denied = handle(database, {"jsonrpc": "2.0", "id": 2,
                                   "method": "resources/read", "params": {"uri": uri}},
                        workspace)
        assert denied["error"]["code"] == -32602
    spoofed = handle(database, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "get_evidence", "arguments": {
                                   "sha256": local_sha, "page": 1, "user_id": "local-dev"}}},
                     workspace)
    assert spoofed["result"]["isError"] is True


def test_reconcile_update_and_delete_clean_versions_and_acl_visibility(tmp_path):
    database, root, rows = _index_docs(tmp_path, [
        ("owned.pdf", "oldworkspaceversion marker and enough synthetic source text. " * 12),
    ])
    create_collection(database, "workspace-b", "workspace-b-user")
    conn = open_database(database)
    try:
        old_version = conn.execute("SELECT version_id FROM paper_versions").fetchone()["version_id"]
    finally:
        conn.close()
    assign_version_to_collection(database, old_version, "workspace-b")
    assert authorized_version_ids(database, "workspace-b-user") == {old_version}
    assert authorized_version_ids(database, "local-dev") == set()

    source = root / "owned.pdf"
    new_sha = _write_pdf(source, "owned revised", "newworkspaceversion marker with revised synthetic evidence. " * 12)
    selection = tmp_path / "selection.jsonl"
    updated = {**rows[0], "sha256": new_sha}
    selection.write_text(json.dumps(updated) + "\n", encoding="utf-8")
    assert index_selection(database, tmp_path / "sources.yaml", selection, reconcile=True)["added"] == 1
    conn = open_database(database, readonly=True)
    try:
        current_version = conn.execute("SELECT version_id FROM paper_versions WHERE sha256=?",
                                       (new_sha,)).fetchone()["version_id"]
        assert conn.execute("SELECT count(*) FROM paper_versions WHERE sha256=?",
                            (rows[0]["sha256"],)).fetchone()[0] == 0
    finally:
        conn.close()
    assert authorized_version_ids(database, "workspace-b-user") == {current_version}
    assert authorized_version_ids(database, "local-dev") == set()
    assert search(database, "newworkspaceversion", principal_id="workspace-b-user")
    assert search(database, "oldworkspaceversion", principal_id="workspace-b-user") == []
    try:
        read_evidence(database, rows[0]["sha256"], 1, Principal("workspace-b-user"))
    except ValueError as exc:
        assert str(exc) == "original paper not found"
    else:
        raise AssertionError("replaced version remained readable")

    source.unlink()
    selection.write_text("", encoding="utf-8")
    assert index_selection(database, tmp_path / "sources.yaml", selection, reconcile=True)["added"] == 0
    assert authorized_version_ids(database, "workspace-b-user") == set()
    assert search(database, "newworkspaceversion", principal_id="workspace-b-user") == []
    try:
        read_evidence(database, new_sha, 1, Principal("workspace-b-user"))
    except ValueError as exc:
        assert str(exc) == "original paper not found"
    else:
        raise AssertionError("deleted version remained readable")


def test_replaced_and_deleted_citations_expire_and_incremental_rebuild_recovers(tmp_path):
    database, root, rows = _index_docs(tmp_path, [
        ("versioned.pdf", "Versionoldmarker establishes the original synthetic calibration baseline."),
    ])
    source = root / "versioned.pdf"
    selection = tmp_path / "selection.jsonl"
    config = tmp_path / "sources.yaml"
    old_sha = rows[0]["sha256"]
    old_result = ask(database, "What does Versionoldmarker establish?", mode="bm25", generate=False)
    assert old_result["status"] == "verified_excerpts"
    old_citation = old_result["claims"][0]["evidence"]
    assert old_citation["sha256"] == old_sha
    assert _validate_quote(old_citation["path"], old_sha, old_citation["pdf_page"],
                           old_citation["quote"], {})

    revised_bytes_hash = _write_pdf(
        source, "versioned revised", "Versionnewmarker establishes the revised synthetic recovery baseline.")
    revised_bytes = source.read_bytes()
    revised_row = {**rows[0], "sha256": revised_bytes_hash}
    selection.write_text(json.dumps(revised_row) + "\n", encoding="utf-8")
    assert not _validate_quote(old_citation["path"], old_sha, old_citation["pdf_page"],
                               old_citation["quote"], {})
    assert old_sha not in {row["sha256"] for row in search_papers(
        database, "Versionoldmarker", Principal("local-dev"))}
    assert old_sha not in {row["sha256"] for row in retrieve(
        database, "Versionoldmarker", source_type="original_pdf", mode="bm25")}
    stale_qa = ask(database, "What does Versionoldmarker establish?", mode="bm25", generate=False)
    assert stale_qa["status"] == "abstained" and stale_qa["claims"] == []
    with pytest.raises(ValueError, match="source file changed or is unavailable"):
        read_evidence(database, old_sha, old_citation["pdf_page"], Principal("local-dev"))

    assert index_selection(database, config, selection, reconcile=True)["added"] == 1
    conn = open_database(database, readonly=True)
    try:
        assert conn.execute("SELECT count(*) FROM paper_versions WHERE sha256=?", (old_sha,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM chunks c JOIN paper_versions v USING(version_id) "
                            "WHERE v.sha256=?", (old_sha,)).fetchone()[0] == 0
    finally:
        conn.close()


    assert search(database, "Versionoldmarker", source_type="original_pdf") == []
    with pytest.raises(ValueError, match="original paper not found"):
        read_evidence(database, old_sha, old_citation["pdf_page"], Principal("local-dev"))

    new_result = ask(database, "What does Versionnewmarker establish?", mode="bm25", generate=False)
    assert new_result["status"] == "verified_excerpts"
    new_citation = new_result["claims"][0]["evidence"]
    assert new_citation["sha256"] == revised_bytes_hash
    assert _validate_quote(new_citation["path"], revised_bytes_hash, new_citation["pdf_page"],
                           new_citation["quote"], {})
    assert index_selection(database, config, selection, reconcile=True)["added"] == 0

    source.unlink()
    deleted_qa = ask(database, "What does Versionnewmarker establish?", mode="bm25", generate=False)
    assert deleted_qa["status"] == "abstained" and deleted_qa["claims"] == []
    assert revised_bytes_hash not in {row["sha256"] for row in search_papers(
        database, "Versionnewmarker", Principal("local-dev"))}
    assert revised_bytes_hash not in {row["sha256"] for row in retrieve(
        database, "Versionnewmarker", source_type="original_pdf", mode="bm25")}
    selection.write_text("", encoding="utf-8")
    assert index_selection(database, config, selection, reconcile=True)["added"] == 0
    assert not _validate_quote(new_citation["path"], revised_bytes_hash, new_citation["pdf_page"],
                               new_citation["quote"], {})
    assert search(database, "Versionnewmarker", source_type="original_pdf") == []
    conn = open_database(database, readonly=True)
    try:
        assert conn.execute("SELECT count(*) FROM paper_versions WHERE sha256=?",
                            (revised_bytes_hash,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM chunks c JOIN paper_versions v USING(version_id) "
                            "WHERE v.sha256=?", (revised_bytes_hash,)).fetchone()[0] == 0
    finally:
        conn.close()
    with pytest.raises(ValueError, match="original paper not found"):
        read_evidence(database, revised_bytes_hash, new_citation["pdf_page"], Principal("local-dev"))

    source.write_bytes(revised_bytes)
    selection.write_text(json.dumps(revised_row) + "\n", encoding="utf-8")
    assert index_selection(database, config, selection, reconcile=True)["added"] == 1
    restored = ask(database, "What does Versionnewmarker establish?", mode="bm25", generate=False)
    assert restored["status"] == "verified_excerpts"
    restored_citation = restored["claims"][0]["evidence"]
    assert restored_citation["sha256"] == revised_bytes_hash
    assert _validate_quote(restored_citation["path"], revised_bytes_hash,
                           restored_citation["pdf_page"], restored_citation["quote"], {})
    conn = open_database(database, readonly=True)
    try:
        assert conn.execute("SELECT count(*) FROM paper_versions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] > 0
    finally:
        conn.close()


def test_web_export_direct_read_and_mcp_share_acl_and_render_verified_evidence(tmp_path):
    database, _root, rows = _index_docs(tmp_path, [
        ("visible.pdf", "Interfaceprobe provides synthetic evidence for a measured result."),
    ])
    create_collection(database, "workspace-b", "workspace-b-user")
    conn = open_database(database)
    try:
        version_id = conn.execute("SELECT version_id FROM paper_versions").fetchone()["version_id"]
    finally:
        conn.close()
    assign_version_to_collection(database, version_id, "workspace-b")
    principal = Principal("workspace-b-user")
    result = ask(database, "What does Interfaceprobe provide?", generate=False,
                 principal_id=principal.user_id)
    assert result["status"] == "verified_excerpts"
    citation = result["claims"][0]["evidence"]
    client = create_app(database, principal_provider=lambda: principal).test_client()
    page = client.get(f"/?conversation_id={result['conversation_id']}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert citation["quote"] in html
    assert f"版本 {version_id}" in html
    assert f"PDF 第 {citation['pdf_page']} 页" in html
    assert "覆盖审查：未执行" in html

    exported = client.get(f"/api/answer-eval/{result['conversation_id']}.jsonl")
    assert exported.status_code == 200
    record = json.loads(exported.data.decode().splitlines()[0])
    evidence = record["claims"][0]["evidence"][0]
    assert evidence["source_sha256"] == citation["sha256"]
    assert evidence["pdf_page"] == citation["pdf_page"]
    assert evidence["snippet"] == citation["quote"]
    assert record["coverage_complete"] is None
    assert "path" not in evidence and "absolute_path" not in evidence

    uri = f"papertrail://evidence/{citation['sha256']}/{citation['pdf_page']}"
    mcp = handle(database, {"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                            "params": {"uri": uri}}, principal)
    assert citation["quote"] in mcp["result"]["contents"][0]["text"]
    denied = create_app(database, principal_provider=lambda: Principal("local-dev")).test_client()
    assert denied.get(f"/api/evidence/{citation['sha256']}/{citation['pdf_page']}").status_code == 404
    assert denied.get(f"/api/answer-eval/{result['conversation_id']}.jsonl").status_code == 404
    denied_mcp = handle(database, {"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                                   "params": {"uri": uri}}, Principal("local-dev"))
    assert denied_mcp["error"]["code"] == -32602
