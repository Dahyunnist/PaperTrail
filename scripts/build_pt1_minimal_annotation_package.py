"""Build a five-row annotation handoff from CSV and source metadata only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ANNOTATION_FIELDS = ["question_type", "answerability", "expected_answer", "quote",
                     "evidence_pdf_pages", "original_pdf_excerpt", "span_start_char",
                     "span_end_char", "annotator", "reviewer", "review_status", "notes"]


def build(csv_path: Path, source_manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    by_sha = {row["pdf_sha256"]: row for row in manifest["sources"]}
    records = []
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            source = by_sha.get(row["pdf_sha256"])
            if not source:
                raise ValueError(f"{row.get('task_id')}: source SHA is not in manifest")
            # Never serialize local_pdf, DOI, title, or any PDF-derived text.
            records.append({
                "task_id": row["task_id"],
                "source_id": "pt1pdf-" + row["pdf_sha256"][:16],
                "pdf_sha256": row["pdf_sha256"],
                "question": row["candidate_question"].strip(),
                "human_fields": {field: None for field in ANNOTATION_FIELDS},
            })
    if len(records) != 5:
        raise ValueError(f"expected exactly five annotation tasks; got {len(records)}")
    if len({row["task_id"] for row in records}) != 5 or len({row["pdf_sha256"] for row in records}) != 5:
        raise ValueError("task IDs and source hashes must be unique")
    return {"schema_version": 1, "package_id": "PT1-human-minimal-5-v1",
            "gold_status": "pending_human_annotation", "tasks": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = build(args.csv, args.manifest)
    args.output.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tasks": len(package["tasks"]), "gold_status": package["gold_status"],
                      "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
