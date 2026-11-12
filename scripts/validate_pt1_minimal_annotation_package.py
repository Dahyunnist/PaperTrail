"""Validate a minimal PT1 handoff without opening PDFs or source paths."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ANNOTATION_FIELDS = ["question_type", "answerability", "expected_answer", "quote",
                     "evidence_pdf_pages", "original_pdf_excerpt", "span_start_char",
                     "span_end_char", "annotator", "reviewer", "review_status", "notes"]


def validate(path: Path) -> list[str]:
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"package unavailable or invalid: {type(exc).__name__}"]
    issues = []
    if package.get("schema_version") != 1 or package.get("gold_status") != "pending_human_annotation":
        issues.append("package version/status invalid")
    tasks = package.get("tasks")
    if not isinstance(tasks, list) or len(tasks) not in {5, 40}:
        return [*issues, "package must contain exactly five or forty tasks"]
    allowed = {"task_id", "source_id", "pdf_sha256", "question", "human_fields"}
    for index, task in enumerate(tasks, 1):
        if set(task) != allowed:
            issues.append(f"task {index}: unexpected or missing top-level fields")
        if not re.fullmatch(r"[0-9a-f]{64}", str(task.get("pdf_sha256", ""))):
            issues.append(f"task {index}: invalid PDF SHA-256")
        if task.get("source_id") != "pt1pdf-" + str(task.get("pdf_sha256", ""))[:16]:
            issues.append(f"task {index}: source_id does not match hash")
        if not isinstance(task.get("question"), str) or not task["question"].strip():
            issues.append(f"task {index}: question missing")
        fields = task.get("human_fields")
        if not isinstance(fields, dict) or set(fields) != set(ANNOTATION_FIELDS):
            issues.append(f"task {index}: human field set invalid")
        elif any(value not in (None, "") for value in fields.values()):
            issues.append(f"task {index}: gold field must remain blank")
    if len({row.get("task_id") for row in tasks}) != len(tasks):
        issues.append("task IDs must be unique")
    expected_id = f"PT1-human-minimal-{len(tasks)}-v1"
    if package.get("package_id") != expected_id:
        issues.append("package_id does not match task count")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    issues = validate(args.package)
    if issues:
        print("\n".join(issues))
        raise SystemExit(1)
    package = json.loads(args.package.read_text(encoding="utf-8"))
    print(f"PT1 minimal package valid: {len(package['tasks'])} tasks; gold fields blank; PDFs not opened.")


if __name__ == "__main__":
    main()
