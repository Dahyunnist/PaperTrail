import hashlib
import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_pt1_gold_jsonl as validator


def make_fixture(tmp_path):
    pdf = tmp_path / "paper.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This study reports 12 samples.")
    doc.save(pdf)
    doc.close()
    text = pymupdf.open(pdf)[0].get_text("text")
    quote = "This study reports 12 samples."
    start = text.index(quote)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    manifest = {"sources": [{"doi": "10.1234/example", "local_pdf": "paper.pdf", "pdf_sha256": digest}]}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    row = {"id": "PT1-001", "paper_ids": ["10.1234/example"], "split": "development",
           "question_type": "fact_location", "question": "How many samples did the study report?",
           "expected_answer": "It reported 12 samples.", "answerability": "answerable",
           "evidence": [{"doi": "10.1234/example", "pdf_sha256": digest, "pdf_page": 1,
                         "start_char": start, "end_char": start + len(quote), "quote": quote, "relation": "supports"}],
           "minimumCompleteEvidenceSet": True, "annotation_status": "human_verified",
           "annotator": "A", "reviewer": "B"}
    jsonl = tmp_path / "gold.jsonl"
    jsonl.write_text(json.dumps(row) + "\n", encoding="utf-8")
    validator.ROOT = tmp_path
    return jsonl, manifest_path, row


def test_pt1_jsonl_accepts_verified_exact_quote(tmp_path):
    jsonl, manifest, _ = make_fixture(tmp_path)
    assert validator.validate(jsonl, manifest, min_questions=1, min_papers=1) == []


def test_pt1_jsonl_rejects_wrong_quote_and_same_reviewer(tmp_path):
    jsonl, manifest, row = make_fixture(tmp_path)
    row["evidence"][0]["quote"] = "invented quote"
    row["reviewer"] = row["annotator"]
    jsonl.write_text(json.dumps(row) + "\n", encoding="utf-8")

    issues = validator.validate(jsonl, manifest, min_questions=1, min_papers=1)

    assert any("quote/span does not match" in issue for issue in issues)
    assert any("reviewer matches annotator" in issue for issue in issues)


def test_pt1_jsonl_rejects_duplicate_questions(tmp_path):
    jsonl, manifest, row = make_fixture(tmp_path)
    duplicate = dict(row, id="PT1-002", question=row["question"].upper())
    jsonl.write_text("\n".join(json.dumps(item) for item in (row, duplicate)) + "\n", encoding="utf-8")

    issues = validator.validate(jsonl, manifest, min_questions=2, min_papers=1)

    assert any("duplicate normalized question" in issue for issue in issues)
