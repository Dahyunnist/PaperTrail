"""Validate the PT-1 human annotation task has no prefilled gold."""
from __future__ import annotations
import csv
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "evals/pt1-human-annotation-task-40-20261111.csv"
MANIFEST = ROOT / "evals/pt1-candidate-manifest-20261111.json"
REQUIRED = {
    "task_id", "paper_split", "doi", "title", "pdf_sha256", "candidate_type",
    "candidate_question", "candidate_basis", "candidate_basis_pdf_page", "question_type", "answerability",
    "expected_answer", "minimal_complete_evidence_quote", "evidence_pdf_pages",
    "original_pdf_excerpt", "span_start_char", "span_end_char", "annotator", "reviewer",
    "review_status", "notes",
}
GOLD_FIELDS = {
    "question_type", "answerability", "expected_answer", "minimal_complete_evidence_quote", "evidence_pdf_pages",
    "original_pdf_excerpt", "span_start_char", "span_end_char", "annotator", "reviewer",
    "review_status",
}


def validate(task_path: Path = TASK, manifest_path: Path = MANIFEST) -> list[str]:
    errors: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_map = {source["doi"]: source for source in manifest["sources"]}
    with task_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != REQUIRED:
            return ["CSV schema mismatch"]
        rows = list(reader)
    if len(rows) != 40:
        errors.append(f"expected 40 rows, got {len(rows)}")
    ids = [row["task_id"] for row in rows]
    if len(set(ids)) != len(ids):
        errors.append("task_id values must be unique")
    dois = {row["doi"] for row in rows}
    if len(dois) != 30:
        errors.append(f"expected 30 isolated paper DOIs, got {len(dois)}")
    questions = ["".join(ch for ch in unicodedata.normalize("NFKC", row["candidate_question"]).casefold() if ch.isalnum()) for row in rows]
    if len(set(questions)) != len(questions):
        errors.append("candidate questions must be unique after normalization")
    for row in rows:
        source = source_map.get(row["doi"])
        if not source:
            errors.append(f"unknown DOI: {row['doi']}")
            continue
        if row["paper_split"] != "development_seen" or row["pdf_sha256"] != source["pdf_sha256"]:
            errors.append(f"paper split or PDF hash mismatch: {row['task_id']}")
        if not row["candidate_question"].strip() or not row["candidate_basis"].strip():
            errors.append(f"candidate prompt missing: {row['task_id']}")
        if any(row[field].strip() for field in GOLD_FIELDS):
            errors.append(f"gold/annotation field must remain blank: {row['task_id']}")
    return errors


if __name__ == "__main__":
    issues = validate()
    if issues:
        print("\n".join(issues))
        raise SystemExit(1)
    print("PT1 human task valid: 40 prompts, 30 DOIs, all gold fields blank.")
