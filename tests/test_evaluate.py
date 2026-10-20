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
