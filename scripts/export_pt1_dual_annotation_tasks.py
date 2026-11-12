"""Export two independent PT-1 fillable CSVs and a grouped frozen source list."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIELDS = ("title", "doi", "year", "source_version", "public_record", "download_url",
                "license", "license_statement", "license_evidence", "license_policy",
                "license_version_url", "pdf_sha256", "paper_split")
REQUIRED_SOURCE_FIELDS = set(SOURCE_FIELDS) - {"source_version"}
ANNOTATION_FIELDS = ("question", "answerability", "expected_answer", "minimum_complete_evidence_set",
                     "evidence", "annotator_id", "independent")
TEMPLATE_GOLD_FIELDS = ("question_type", "answerability", "expected_answer",
                        "minimal_complete_evidence_quote", "evidence_pdf_pages", "original_pdf_excerpt",
                        "span_start_char", "span_end_char", "annotator", "reviewer", "review_status", "notes")
CSV_FIELDS = ("annotation_slot", "task_id", "source_id", "paper_split", "doi", "title", "year",
              "source_version", "pdf_sha256", "public_record", "download_url", "license",
              "license_statement", "license_evidence", "license_policy", "license_version_url",
              "candidate_type", "candidate_question", "candidate_basis", "candidate_basis_pdf_page",
              "question_type",
              *ANNOTATION_FIELDS)


def _sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build(tasks_path: Path, manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {source["doi"]: source for source in manifest.get("sources", [])}
    grouped: dict[str, dict[str, Any]] = {}
    export_rows: list[dict[str, str]] = []
    with tasks_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"task_id", "paper_split", "doi", "title", "pdf_sha256", "candidate_type",
                    "candidate_question", "candidate_basis", "candidate_basis_pdf_page", *TEMPLATE_GOLD_FIELDS}
        if not required <= set(reader.fieldnames or []):
            raise ValueError("PT1 task CSV schema mismatch")
        tasks = list(reader)
    if len(tasks) != 40:
        raise ValueError(f"expected 40 questions, got {len(tasks)}")
    if len({row["task_id"] for row in tasks}) != len(tasks):
        raise ValueError("task IDs must be unique")
    for task in tasks:
        task_id, doi = task["task_id"], task["doi"]
        source = sources.get(doi)
        if not source or task["pdf_sha256"] != source.get("pdf_sha256"):
            raise ValueError(f"{task_id}: task DOI/PDF SHA does not match source manifest")
        if task["paper_split"] != source.get("paper_split"):
            raise ValueError(f"{task_id}: task split does not match source manifest")
        if any(task.get(field, "").strip() for field in TEMPLATE_GOLD_FIELDS):
            raise ValueError(f"{task_id}: task template contains prefilled annotation data")
        if not task["candidate_question"].strip():
            raise ValueError(f"{task_id}: candidate question is empty")
        group = grouped.setdefault(doi, {"source": source, "tasks": []})
        group["tasks"].append(task)
        export_rows.append(task)
    paper_count = len(grouped)
    if not 30 <= paper_count <= 60:
        raise ValueError(f"expected 30-60 distinct papers, got {paper_count}")
    if len(sources) != manifest.get("source_count", len(sources)):
        raise ValueError("candidate source_count does not match source records")

    frozen_sources: list[dict[str, Any]] = []
    for doi in sorted(grouped):
        source = grouped[doi]["source"]
        missing = [field for field in REQUIRED_SOURCE_FIELDS if not source.get(field)]
        if missing:
            raise ValueError(f"source {doi}: missing public provenance fields: {', '.join(sorted(missing))}")
        source_record = {field: source.get(field, "") for field in SOURCE_FIELDS}
        source_record["source_id"] = "pt1pdf-" + str(source["pdf_sha256"])[:16]
        source_record["task_ids"] = sorted(row["task_id"] for row in grouped[doi]["tasks"])
        frozen_sources.append(source_record)

    frozen = {
        "schema_version": 1,
        "status": "frozen_tasks_pending_human_annotations",
        "dataset_id": manifest.get("dataset_id"),
        "frozen_at": manifest.get("frozen_at"),
        "task_csv_sha256": _sha256(tasks_path),
        "source_manifest_sha256": _sha256(manifest_path),
        "question_count": len(tasks),
        "paper_count": paper_count,
        "paper_count_plan": {"minimum": 30, "maximum": 60},
        "gold_status": "pending_human_annotation",
        "source_groups": frozen_sources,
    }
    return frozen, export_rows


def export(tasks_path: Path, manifest_path: Path, output_dir: Path,
           prefix: str = "pt1-dual-annotation-40") -> dict[str, Path]:
    frozen, rows = build(tasks_path, manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"annotator_a": output_dir / f"{prefix}-a.csv",
               "annotator_b": output_dir / f"{prefix}-b.csv",
               "frozen": output_dir / f"{prefix}-frozen-grouped.json"}
    for slot, key in (("A", "annotator_a"), ("B", "annotator_b")):
        with outputs[key].open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for task in sorted(rows, key=lambda row: (row["doi"], row["task_id"])):
                source = next(item for item in frozen["source_groups"] if item["doi"] == task["doi"])
                record = {field: "" for field in CSV_FIELDS}
                record.update({"annotation_slot": slot, "task_id": task["task_id"],
                    "source_id": source["source_id"], "paper_split": task["paper_split"],
                    "doi": source["doi"], "title": source["title"], "year": str(source["year"]),
                    "source_version": source["source_version"], "pdf_sha256": source["pdf_sha256"],
                    "public_record": source["public_record"], "download_url": source["download_url"],
                    "license": source["license"], "license_statement": source["license_statement"],
                    "license_evidence": source["license_evidence"], "license_policy": source["license_policy"],
                    "license_version_url": source["license_version_url"],
                    "candidate_type": task["candidate_type"],
                    "candidate_question": task["candidate_question"], "candidate_basis": task["candidate_basis"],
                    "candidate_basis_pdf_page": task["candidate_basis_pdf_page"],
                    "question": task["candidate_question"]})
                writer.writerow(record)
    outputs["frozen"].write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return outputs


def validate_frozen(frozen_path: Path, tasks_path: Path, manifest_path: Path) -> list[str]:
    try:
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        expected, _ = build(tasks_path, manifest_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [f"frozen list input invalid: {type(exc).__name__}: {exc}"]
    if frozen != expected:
        return ["frozen grouped list does not match task CSV and source manifest"]
    if frozen.get("question_count") != 40:
        return ["frozen list must contain exactly 40 questions"]
    if not 30 <= frozen.get("paper_count", 0) <= 60:
        return ["frozen list must cover 30-60 papers"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="导出两份独立填写表和按论文分组冻结清单")
    export_parser.add_argument("--tasks", type=Path, required=True)
    export_parser.add_argument("--manifest", type=Path, required=True)
    export_parser.add_argument("--output-dir", type=Path, required=True)
    export_parser.add_argument("--prefix", default="pt1-dual-annotation-40")
    validate_parser = subparsers.add_parser("validate", help="校验冻结清单与权威空白输入一致")
    validate_parser.add_argument("frozen", type=Path)
    validate_parser.add_argument("--tasks", type=Path, required=True)
    validate_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export":
        outputs = export(args.tasks, args.manifest, args.output_dir, args.prefix)
        print(json.dumps({key: str(path) for key, path in outputs.items()}, ensure_ascii=False))
        return 0
    issues = validate_frozen(args.frozen, args.tasks, args.manifest)
    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 1
    frozen = json.loads(args.frozen.read_text(encoding="utf-8"))
    print(f"PT1 frozen list valid: {frozen['question_count']} questions, {frozen['paper_count']} papers; PDFs not opened; gold pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
