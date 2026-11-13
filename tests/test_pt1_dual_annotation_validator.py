import csv
import copy
import hashlib
import json
import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_pt1_dual_annotations as validator


def _fixture(tmp_path, monkeypatch):
    pdf_path = tmp_path / "synthetic.pdf"
    document = pymupdf.open()
    page = document.new_page()
    text = "Synthetic trial enrolled 12 people. Follow-up lasted 3 months."
    page.insert_text((72, 72), text)
    document.save(pdf_path)
    document.close()
    with pymupdf.open(pdf_path) as check:
        page_text = check[0].get_text("text")
    quote = "Synthetic trial enrolled 12 people."
    start = page_text.index(quote)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    tasks_path = tmp_path / "tasks.csv"
    with tasks_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["task_id", "doi", "pdf_sha256", "candidate_question"])
        writer.writeheader()
        writer.writerow({"task_id": "PT1-H001", "doi": "10.9999/synthetic", "pdf_sha256": digest,
                         "candidate_question": "How many people were enrolled?"})
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"sources": [{"doi": "10.9999/synthetic",
        "local_pdf": "synthetic.pdf", "pdf_sha256": digest}]}), encoding="utf-8")
    base = {"task_id": "PT1-H001", "independent": True, "doi": "10.9999/synthetic",
            "pdf_sha256": digest, "question": "How many people were enrolled?",
            "question_type": "fact_location",
            "answerability": "answerable", "expected_answer": "12 people.",
            "minimum_complete_evidence_set": True,
            "evidence": [{"doi": "10.9999/synthetic", "pdf_sha256": digest, "pdf_page": 1,
                          "start_char": start, "end_char": start + len(quote), "quote": quote,
                          "relation": "supports"}]}
    annotations_path = tmp_path / "annotations.jsonl"
    rows = [copy.deepcopy(base) | {"annotator_id": "annotator-a"},
            copy.deepcopy(base) | {"annotator_id": "annotator-b"}]
    annotations_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    return annotations_path, tasks_path, manifest_path, rows, digest


def test_two_independent_annotations_validate_but_are_not_gold(tmp_path, monkeypatch):
    annotations, tasks, manifest, _, _ = _fixture(tmp_path, monkeypatch)
    issues, report = validator.validate(annotations, tasks, manifest)
    assert issues == []
    assert report == [{"task_id": "PT1-H001", "status": "agreement_pending_final_review",
                       "annotator_ids": ["annotator-a", "annotator-b"], "conflicts": []}]
    assert "expected_answer" not in report[0]


def test_validator_accepts_the_two_fillable_csv_exports(tmp_path, monkeypatch):
    _, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    csv_paths = []
    fields = sorted(validator.REQUIRED | {"question_type"})
    for row in rows:
        path = tmp_path / f"{row['annotator_id']}.csv"
        csv_row = dict(row)
        csv_row["independent"] = "true"
        csv_row["minimum_complete_evidence_set"] = "true"
        csv_row["evidence"] = json.dumps(csv_row["evidence"])
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerow(csv_row)
        csv_paths.append(path)
    issues, report = validator.validate(csv_paths, tasks, manifest)
    assert issues == []
    assert report[0]["status"] == "agreement_pending_final_review"


def test_disagreement_is_pending_adjudication_without_merging_answers(tmp_path, monkeypatch):
    annotations, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    rows[1]["answerability"] = "unanswerable"
    rows[1]["question_type"] = "unanswerable"
    rows[1]["expected_answer"] = "The report is not stated."
    rows[1]["evidence"] = []
    annotations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    issues, report = validator.validate(annotations, tasks, manifest)
    assert issues == []
    assert report[0]["status"] == "pending_adjudication"
    assert {"answerability", "expected_answer", "question_type", "minimum_evidence_set"} <= set(report[0]["conflicts"])
    assert "answer" not in report[0] and "expected_answer" not in report[0]


def test_validator_requires_two_distinct_independent_annotators(tmp_path, monkeypatch):
    annotations, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    annotations.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    issues, report = validator.validate(annotations, tasks, manifest)
    assert any("at least two distinct annotators required" in issue for issue in issues)
    assert report[0]["status"] == "insufficient_independent_annotations"


def test_validator_rejects_duplicate_evidence_and_marks_row_invalid(tmp_path, monkeypatch):
    annotations, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    rows[0]["evidence"].append(copy.deepcopy(rows[0]["evidence"][0]))
    annotations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    issues, report = validator.validate(annotations, tasks, manifest)
    assert any("duplicate evidence reference" in issue for issue in issues)
    assert report[0]["status"] == "invalid_annotations"


def test_blank_annotator_id_marks_task_invalid(tmp_path, monkeypatch):
    annotations, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    rows[0]["annotator_id"] = " "
    annotations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    issues, report = validator.validate(annotations, tasks, manifest)
    assert any("annotator_id must be nonempty" in issue for issue in issues)
    assert report[0]["status"] == "invalid_annotations"


def test_cli_writes_conflicts_as_pending_without_annotation_content(tmp_path, monkeypatch):
    annotations, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    rows[1]["expected_answer"] = "A different synthetic answer."
    annotations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    report_path = tmp_path / "report.jsonl"
    monkeypatch.setattr(sys, "argv", ["validate_pt1_dual_annotations.py", str(annotations),
        "--tasks", str(tasks), "--manifest", str(manifest), "--report", str(report_path)])
    assert validator.main() == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pending_adjudication"
    assert "expected_answer" in report["conflicts"]
    assert "12 people" not in report_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("field,value,expected", [
    ("pdf_sha256", "0" * 64, "annotation PDF SHA-256 mismatch"),
    ("minimum_complete_evidence_set", False, "minimum complete evidence set must be explicitly attested"),
    ("answerability", "guess", "invalid answerability"),
])
def test_validator_rejects_invalid_annotation_claims(tmp_path, monkeypatch, field, value, expected):
    annotations, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    rows[0][field] = value
    annotations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    issues, report = validator.validate(annotations, tasks, manifest)
    assert any(expected in issue for issue in issues)
    assert report[0]["status"] == "invalid_annotations"


def test_validator_rejects_wrong_page_and_source_span(tmp_path, monkeypatch):
    annotations, tasks, manifest, rows, _ = _fixture(tmp_path, monkeypatch)
    rows[0]["evidence"][0]["pdf_page"] = 2
    rows[1]["evidence"][0]["start_char"] += 1
    annotations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    issues, _ = validator.validate(annotations, tasks, manifest)
    assert any("evidence PDF page out of range" in issue for issue in issues)
    assert any("quote/span does not exactly match" in issue for issue in issues)


def test_existing_blank_task_template_stays_empty():
    sys.path.insert(0, str(ROOT / "scripts"))
    import validate_pt1_human_annotation_task as blank_template_validator
    assert blank_template_validator.validate() == []


def test_input_schema_matches_validator_required_fields():
    schema = json.loads((ROOT / "evals/pt1-dual-annotation-schema-v1.json").read_text(encoding="utf-8"))
    assert set(schema["required"]) == validator.REQUIRED
