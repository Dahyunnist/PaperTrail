"""Validate a five-case draft; never create or certify gold automatically."""
from __future__ import annotations

import json
import argparse
import re
from pathlib import Path
from typing import Any

FIELDS = {"question_type", "answerability", "expected_answer", "minimum_evidence",
          "support_conflict", "evidence_page", "evidence_locator", "annotator_a",
          "annotator_b", "independent_a", "independent_b", "adjudication", "review_status"}


def validate(rows: list[dict[str, Any]]) -> list[str]:
    issues = []
    if len(rows) != 5 or len({row.get("task_id") for row in rows}) != 5:
        issues.append("exactly five unique cases required")
    for row in rows:
        if row.get("status") == "draft":
            continue
        if row.get("status") != "gold":
            issues.append(f"{row.get('task_id')}: status must be draft or gold")
            continue
        source = row.get("source", {})
        if not isinstance(source, dict) or any(source.get(key) in (None, "", "pending")
                for key in ("pdf_path", "pdf_sha256", "evidence_page", "evidence_locator")):
            issues.append(f"{row.get('task_id')}: source locator incomplete")
        elif (not re.fullmatch(r"[0-9a-f]{64}", str(source["pdf_sha256"]))
              or not isinstance(source["evidence_page"], int) or source["evidence_page"] < 1):
            issues.append(f"{row.get('task_id')}: source hash/page invalid")
        annotations = row.get("annotations", [])
        if len(annotations) != 2 or len({a.get("annotator") for a in annotations}) != 2:
            issues.append(f"{row.get('task_id')}: two distinct annotators required")
            continue
        if any(a.get("independent") is not True or not FIELDS.issubset(a)
               or any(a.get(key) in (None, "") for key in FIELDS) for a in annotations):
            issues.append(f"{row.get('task_id')}: independent annotations incomplete")
        if row.get("adjudication") != "resolved":
            issues.append(f"{row.get('task_id')}: adjudication unresolved")
    return issues


def validate_file(path: Path) -> list[str]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return validate(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    args = parser.parse_args()
    issues = validate_file(args.jsonl)
    if issues:
        print("\n".join(issues))
        raise SystemExit(1)
    print("5 annotation cases valid; draft cases remain pending; no gold inferred")


if __name__ == "__main__":
    main()
