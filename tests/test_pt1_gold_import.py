import hashlib
import json
import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import import_pt1_gold_jsonl as importer
import validate_pt1_gold_jsonl as validator
from papertrail.gold import load_gold, verify_quotes


def _make_pdf(path: Path, text: str) -> tuple[str, str, int]:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    doc = pymupdf.open(path)
    page_text = doc[0].get_text("text")
    doc.close()
    start = page_text.index(text)
    return hashlib.sha256(path.read_bytes()).hexdigest(), text, start


def _fixture(tmp_path, monkeypatch):
    sources = []
    texts = ["The measured outcome increased.", "The measured outcome decreased.", "No follow-up duration was reported."]
    for index, text in enumerate(texts, 1):
        path = tmp_path / f"paper-{index}.pdf"
        digest, quote, start = _make_pdf(path, text)
        sources.append({"doi": f"10.1234/paper{index}", "local_pdf": path.name, "pdf_sha256": digest,
                        "quote": quote, "start": start})
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    conflict = {
        "id": "PT1-001", "paper_ids": [sources[0]["doi"], sources[1]["doi"]], "split": "development",
        "question_type": "conflict", "question": "What results did the studies report?",
        "expected_answer": "The first reported an increase; the second reported a decrease.",
        "answerability": "answerable", "minimumCompleteEvidenceSet": True,
        "annotation_status": "human_verified", "annotator": "annotator", "reviewer": "reviewer",
        "evidence": [
            {"doi": source["doi"], "pdf_sha256": source["pdf_sha256"], "pdf_page": 1,
             "start_char": source["start"], "end_char": source["start"] + len(source["quote"]),
             "quote": source["quote"], "relation": relation}
            for source, relation in zip(sources[:2], ("supports", "contradicts"))
        ],
    }
    refusal = {
        "id": "PT1-002", "paper_ids": [sources[2]["doi"]], "split": "development",
        "question_type": "unanswerable", "question": "Was a ten-year outcome reported?",
        "expected_answer": "Cannot answer: the paper does not report a ten-year outcome.",
        "answerability": "unanswerable", "minimumCompleteEvidenceSet": True,
        "annotation_status": "human_verified", "annotator": "annotator", "reviewer": "reviewer",
        "evidence": [],
    }
    v2_path = tmp_path / "human-v2.jsonl"
    v2_path.write_text("\n".join(json.dumps(row) for row in (conflict, refusal)) + "\n", encoding="utf-8")
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    monkeypatch.setattr(importer, "ROOT", tmp_path)
    return v2_path, manifest_path


def test_import_preserves_cross_paper_and_refusal_and_verifies_quotes(tmp_path, monkeypatch):
    v2, manifest = _fixture(tmp_path, monkeypatch)
    output_gold = tmp_path / "runtime-gold.jsonl"
    output_sources = tmp_path / "runtime-sources.yaml"

    count, quote_count = importer.convert(v2, output_gold, output_sources, manifest, min_questions=2, min_papers=3)

    items = load_gold(output_gold, minimum_questions=2)
    assert count == 2
    assert quote_count == 2
    assert [item["question_type"] for item in items] == ["conflict", "unanswerable"]
    assert items[0]["abstain"] is False
    assert [item["relation"] for item in items[0]["evidence"]] == ["supports", "contradicts"]
    assert items[1]["abstain"] is True and items[1]["evidence"] == []
    assert verify_quotes(items, output_sources) == 2


@pytest.mark.parametrize("change", ["pending", "same_reviewer"])
def test_import_rejects_unreviewed_annotations_before_writing(tmp_path, monkeypatch, change):
    v2, manifest = _fixture(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in v2.read_text(encoding="utf-8").splitlines()]
    if change == "pending":
        rows[0]["annotation_status"] = "pending"
    else:
        rows[0]["reviewer"] = rows[0]["annotator"]
    v2.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    output_gold = tmp_path / "runtime-gold.jsonl"
    output_sources = tmp_path / "runtime-sources.yaml"

    with pytest.raises(ValueError, match="PT1 v2 validation failed"):
        importer.convert(v2, output_gold, output_sources, manifest, min_questions=2, min_papers=3)

    assert not output_gold.exists()
    assert not output_sources.exists()


def test_import_rejects_empty_annotations(tmp_path, monkeypatch):
    v2, manifest = _fixture(tmp_path, monkeypatch)
    v2.write_text("", encoding="utf-8")
    output_gold = tmp_path / "runtime-gold.jsonl"
    output_sources = tmp_path / "runtime-sources.yaml"

    with pytest.raises(ValueError, match="expected at least 1 questions, got 0"):
        importer.convert(v2, output_gold, output_sources, manifest, min_questions=1, min_papers=1)

    assert not output_gold.exists()
    assert not output_sources.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pdf_sha256", "0" * 64, "evidence PDF hash mismatch"),
        ("pdf_page", 2, "evidence PDF page out of range"),
        ("start_char", 1, "quote/span does not match"),
    ],
)
def test_import_rejects_invalid_pdf_references(tmp_path, monkeypatch, field, value, message):
    v2, manifest = _fixture(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in v2.read_text(encoding="utf-8").splitlines()]
    rows[0]["evidence"][0][field] = value
    v2.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    output_gold = tmp_path / "runtime-gold.jsonl"
    output_sources = tmp_path / "runtime-sources.yaml"

    with pytest.raises(ValueError, match=message):
        importer.convert(v2, output_gold, output_sources, manifest, min_questions=2, min_papers=3)

    assert not output_gold.exists()
    assert not output_sources.exists()
