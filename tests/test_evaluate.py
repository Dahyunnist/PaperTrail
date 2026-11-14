import hashlib
import json
from pathlib import Path

import fitz
import yaml

from papertrail.evaluate import compare_modes, evaluate
from papertrail.s1_index import index_selection


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gold_evaluation_excludes_personal_notes_and_reports_abstention(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    pdf = root / "source.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "Original Evidence Article", fontsize=16)
    page.insert_text((40, 100), "Evidence anchorterm appears on physical page one with enough distinct words.")
    page = doc.new_page()
    page.insert_text((40, 60), "Another discussion section", fontsize=15)
    page.insert_text((40, 100), "The anchorterm conclusion occurs on this second physical page of source.")
    doc.save(pdf)
    doc.close()
    note = root / "private-note.md"
    note.write_text("# Private note\n\nanchorterm appears in personal memory, not source evidence.\n", encoding="utf-8")
    sources = tmp_path / "sources.yaml"
    sources.write_text(yaml.safe_dump({"roots": [{"id": "root", "path": str(root)}]}), encoding="utf-8")
    manifest = tmp_path / "selection.jsonl"
    manifest.write_text("".join(json.dumps({"root_id": "root", "file_name": p.name,
        "relative_path": p.name, "sha256": _sha(p), "kind": kind,
        "source_type": source_type}) + "\n" for p, kind, source_type in
        ((pdf, "pdf", "original_pdf"), (note, "md", "reading_note"))), encoding="utf-8")
    db = tmp_path / "index.sqlite3"
    index_selection(db, sources, manifest)
    gold = tmp_path / "gold.jsonl"
    records = [
        {"id": "Q1", "question_type": "fact_location", "question": "anchorterm conclusion",
         "expected_answer": "on second page", "abstain": False,
         "evidence": [{"root_id": "root", "file_name": pdf.name, "sha256": _sha(pdf),
                       "pdf_page": 2, "quote": "The anchorterm conclusion occurs on this second physical page of source."}]},
    ]
    records.extend({"id": f"Q{i}", "question_type": "unanswerable",
                    "question": f"unanswerable query {i}", "expected_answer": "unknown",
                    "abstain": True, "evidence": []} for i in range(2, 31))
    gold.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")

    result = evaluate(db, gold, k=1)
    assert result["answerable_questions"] == 1
    assert result["unanswerable_questions"] == 29
    assert all(row["source_type"] == "original_pdf" for row in result["trace"][0]["chunk_results"])
    comparison = compare_modes(db, gold, k=1, modes=("bm25",))
    assert comparison["modes"]["bm25"]["trace"][0]["page_results"]
    assert comparison["modes"]["bm25"]["gold_page_recall_at_k"] == 1.0
    assert comparison["modes"]["bm25"]["complete_evidence_at_k"] == 1.0
    assert comparison["modes"]["bm25"]["trace"][0]["complete_evidence"] is True
    assert comparison["modes"]["bm25"]["trace"][0]["evidence_items_found"] == 1
    assert next(iter(comparison["modes"]["bm25"]["by_paper"].values()))["page_hits"] == 1


def test_multi_page_evidence_is_incomplete_when_only_one_gold_page_is_retrieved(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    pdf = root / "two-page-study.pdf"
    doc = fitz.open()
    first = doc.new_page()
    first.insert_text((40, 60), "Rare amber marker identifies the first required finding.")
    second = doc.new_page()
    second.insert_text((40, 60), "Distinct violet marker identifies the second required finding.")
    doc.save(pdf)
    doc.close()
    digest = _sha(pdf)
    sources = tmp_path / "sources.yaml"
    sources.write_text(yaml.safe_dump({"roots": [{"id": "root", "path": str(root)}]}), encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({"root_id": "root", "file_name": pdf.name,
        "relative_path": pdf.name, "sha256": digest, "kind": "pdf",
        "source_type": "original_pdf"}) + "\n", encoding="utf-8")
    database = tmp_path / "index.sqlite3"
    index_selection(database, sources, selection)
    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({
        "id": "SYN-MULTIPAGE", "question_type": "multi_hop",
        "question": "What does the rare amber marker show?",
        "expected_answer": "Both findings are required.", "abstain": False,
        "evidence": [
            {"root_id": "root", "file_name": pdf.name, "sha256": digest, "pdf_page": 1,
             "quote": "Rare amber marker identifies the first required finding."},
            {"root_id": "root", "file_name": pdf.name, "sha256": digest, "pdf_page": 2,
             "quote": "Distinct violet marker identifies the second required finding."},
        ],
    }) + "\n", encoding="utf-8")

    comparison = compare_modes(database, gold, k=1, modes=("bm25",), minimum_questions=1)
    metrics = comparison["modes"]["bm25"]
    trace = metrics["trace"][0]
    assert trace["page_hit"] is True
    assert trace["all_evidence_pages"] is False
    assert trace["complete_evidence"] is False
    assert trace["evidence_items_found"] == 1
    assert trace["evidence_items_total"] == 2
    assert metrics["all_evidence_pages_at_k"] == 0
    assert metrics["complete_evidence_at_k"] == 0
    assert metrics["evidence_item_recall_at_k"] == 0.5
