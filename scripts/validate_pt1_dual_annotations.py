"""Validate independent offline PT-1 annotations; never resolve disagreements."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = ROOT / "evals/pt1-human-annotation-task-40-20261111.csv"
DEFAULT_MANIFEST = ROOT / "evals/pt1-candidate-manifest-20261111.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ANSWERABILITY = {"answerable", "unanswerable", "ambiguous"}
QUESTION_TYPES = {"fact_location", "method_comparison", "cross_paper", "multi_hop", "conflict", "unanswerable"}
RELATIONS = {"supports", "contradicts", "context"}
REQUIRED = {"task_id", "annotator_id", "independent", "doi", "pdf_sha256", "question", "answerability",
            "expected_answer", "minimum_complete_evidence_set", "evidence"}
EVIDENCE_FIELDS = {"doi", "pdf_sha256", "pdf_page", "start_char", "end_char", "quote", "relation"}


def _normal(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _read_annotations(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    for path in paths:
        if path.suffix.casefold() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not (REQUIRED | {"question_type"}) <= set(reader.fieldnames or []):
                    issues.append(f"{path.name}: annotation CSV schema mismatch")
                    continue
                for line_no, row in enumerate(reader, 2):
                    row["independent"] = row.get("independent", "").strip().casefold() == "true"
                    row["minimum_complete_evidence_set"] = (
                        row.get("minimum_complete_evidence_set", "").strip().casefold() == "true")
                    raw_evidence = row.get("evidence", "").strip()
                    try:
                        row["evidence"] = json.loads(raw_evidence) if raw_evidence else []
                    except json.JSONDecodeError:
                        issues.append(f"{path.name} line {line_no}: invalid evidence JSON")
                        row["evidence"] = None
                    rows.append(row)
        else:
            for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    issues.append(f"{path.name} line {line_no}: invalid JSON")
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    issues.append(f"{path.name} line {line_no}: record must be an object")
    return rows, issues


def validate(annotations_path: Path | list[Path], tasks_path: Path = DEFAULT_TASKS,
             manifest_path: Path = DEFAULT_MANIFEST) -> tuple[list[str], list[dict[str, Any]]]:
    issues: list[str] = []
    tasks: dict[str, dict[str, str]] = {}
    with tasks_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required_task_fields = {"task_id", "doi", "pdf_sha256", "candidate_question"}
        if not required_task_fields <= set(reader.fieldnames or []):
            return ["task CSV schema mismatch"], []
        for row in reader:
            if row["task_id"] in tasks:
                issues.append(f"duplicate task id: {row['task_id']}")
            tasks[row["task_id"]] = row

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {source["doi"]: source for source in manifest.get("sources", [])}
    source_cache: dict[str, tuple[pymupdf.Document, str] | None] = {}
    grouped: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in tasks}

    def source_for(doi: str, task_id: str, annotator_id: str) -> tuple[pymupdf.Document, str] | None:
        if doi in source_cache:
            return source_cache[doi]
        source = sources.get(doi)
        if not source:
            issues.append(f"{task_id}/{annotator_id}: unknown source DOI")
            source_cache[doi] = None
            return None
        pdf_path = (ROOT / source["local_pdf"]).resolve()
        if ROOT.resolve() not in pdf_path.parents:
            issues.append(f"{task_id}/{annotator_id}: source path escapes repository")
            source_cache[doi] = None
            return None
        try:
            digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            if digest != source["pdf_sha256"]:
                issues.append(f"{task_id}/{annotator_id}: manifest PDF SHA-256 mismatch")
                source_cache[doi] = None
                return None
            source_cache[doi] = (pymupdf.open(pdf_path), digest)
        except (OSError, RuntimeError) as exc:
            issues.append(f"{task_id}/{annotator_id}: source PDF unavailable ({type(exc).__name__})")
            source_cache[doi] = None
        return source_cache[doi]

    annotation_paths = annotations_path if isinstance(annotations_path, list) else [annotations_path]
    annotation_rows, input_issues = _read_annotations(annotation_paths)
    issues.extend(input_issues)
    try:
        for line_no, row in enumerate(annotation_rows, 1):
            if REQUIRED - row.keys():
                issues.append(f"annotation {line_no}: missing required annotation fields")
                continue
            task_id, annotator_id = row["task_id"], row["annotator_id"]
            if not isinstance(task_id, str) or task_id not in tasks:
                issues.append(f"line {line_no}: unknown task id")
                continue
            if not isinstance(annotator_id, str) or not annotator_id.strip():
                issues.append(f"line {line_no}: annotator_id must be nonempty")
                annotator_id = f"invalid-line-{line_no}"
            bucket = grouped[task_id]
            if any(item.get("annotator_id") == annotator_id for item in bucket):
                issues.append(f"{task_id}/{annotator_id}: duplicate annotation")
                continue
            bucket.append(row)
            prefix = f"{task_id}/{annotator_id}"
            task = tasks[task_id]
            if row["independent"] is not True:
                issues.append(f"{prefix}: independent annotation attestation required")
            if row["doi"] != task["doi"]:
                issues.append(f"{prefix}: DOI differs from assigned task source")
            task_digest = task["pdf_sha256"]
            source_meta = sources.get(task["doi"])
            if (not isinstance(row["pdf_sha256"], str) or not SHA256.fullmatch(row["pdf_sha256"])
                    or row["pdf_sha256"] != task_digest or not source_meta
                    or row["pdf_sha256"] != source_meta.get("pdf_sha256")):
                issues.append(f"{prefix}: annotation PDF SHA-256 mismatch")
            source_for(task["doi"], task_id, annotator_id)
            question = row["question"]
            if not isinstance(question, str) or not question.strip():
                issues.append(f"{prefix}: question must be nonempty")
            answerability = row["answerability"]
            if not isinstance(answerability, str) or answerability not in ANSWERABILITY:
                issues.append(f"{prefix}: invalid answerability")
            question_type = row.get("question_type")
            if question_type is not None:
                if not isinstance(question_type, str) or question_type not in QUESTION_TYPES:
                    issues.append(f"{prefix}: invalid question_type")
                elif ((answerability == "unanswerable") != (question_type == "unanswerable")
                      and answerability in {"answerable", "unanswerable"}):
                    issues.append(f"{prefix}: question_type must match answerability")
            expected = row["expected_answer"]
            if not isinstance(expected, str) or not expected.strip():
                issues.append(f"{prefix}: expected_answer or refusal rationale required")
            if row["minimum_complete_evidence_set"] is not True:
                issues.append(f"{prefix}: minimum complete evidence set must be explicitly attested")
            evidence = row["evidence"]
            if not isinstance(evidence, list):
                issues.append(f"{prefix}: evidence must be a list")
                evidence = []
            if answerability == "answerable" and not evidence:
                issues.append(f"{prefix}: answerable annotation needs evidence")
            if answerability in {"unanswerable", "ambiguous"} and evidence:
                issues.append(f"{prefix}: non-answerable annotation must not claim supporting evidence")
            if answerability == "ambiguous":
                issues.append(f"{prefix}: ambiguous question needs revision before adjudication")
            for entry in evidence:
                if not isinstance(entry, dict) or EVIDENCE_FIELDS - entry.keys():
                    issues.append(f"{prefix}: evidence reference fields missing")
                    continue
                doi = entry["doi"]
                if not isinstance(doi, str):
                    issues.append(f"{prefix}: evidence DOI must be a string")
                    continue
                if doi != task["doi"]:
                    issues.append(f"{prefix}: evidence DOI differs from assigned task source")
                    continue
                source = sources.get(doi)
                if not source:
                    issues.append(f"{prefix}: unknown source DOI")
                    continue
                digest = entry["pdf_sha256"]
                if (not isinstance(digest, str) or not SHA256.fullmatch(digest)
                        or digest != source["pdf_sha256"] or digest != task["pdf_sha256"]):
                    issues.append(f"{prefix}: evidence PDF SHA-256 mismatch")
                    continue
                document = source_for(doi, task_id, annotator_id)
                if not document:
                    continue
                pdf, _ = document
                page = entry["pdf_page"]
                if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= pdf.page_count:
                    issues.append(f"{prefix}: evidence PDF page out of range")
                    continue
                start, end, quote = entry["start_char"], entry["end_char"], entry["quote"]
                if not isinstance(entry["relation"], str) or entry["relation"] not in RELATIONS:
                    issues.append(f"{prefix}: invalid evidence relation")
                page_text = pdf[page - 1].get_text("text")
                if (not isinstance(start, int) or isinstance(start, bool)
                        or not isinstance(end, int) or isinstance(end, bool)
                        or not isinstance(quote, str) or not quote.strip()
                        or start < 0 or end <= start or end > len(page_text)
                        or page_text[start:end] != quote):
                    issues.append(f"{prefix}: quote/span does not exactly match source PDF page")
    finally:
        for document in source_cache.values():
            if document:
                document[0].close()

    report: list[dict[str, Any]] = []
    for task_id, annotations in grouped.items():
        annotators = sorted(str(row.get("annotator_id", "")) for row in annotations)
        conflicts: set[str] = set()
        invalid = any(issue.startswith(f"{task_id}/") or issue.startswith(f"{task_id}:")
                      for issue in issues)
        if len(set(annotators)) < 2:
            status = "insufficient_independent_annotations"
            issues.append(f"{task_id}: at least two distinct annotators required")
        else:
            if any(row.get("answerability") == "ambiguous" for row in annotations):
                conflicts.add("ambiguous_answerability")
            for field in ("question", "answerability", "expected_answer"):
                values = {_normal(row[field]) if isinstance(row.get(field), str) else "" for row in annotations}
                if len(values) > 1:
                    conflicts.add(field)
            if all("question_type" in row for row in annotations):
                question_types = {row.get("question_type") for row in annotations}
                if len(question_types) > 1:
                    conflicts.add("question_type")
            evidence_sets = {tuple(sorted(json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                                          for item in row.get("evidence", []) if isinstance(item, dict)))
                             for row in annotations}
            if len(evidence_sets) > 1:
                conflicts.add("minimum_evidence_set")
            status = ("invalid_annotations" if invalid else
                      "pending_adjudication" if conflicts else "agreement_pending_final_review")
        report.append({"task_id": task_id, "status": status, "annotator_ids": annotators,
                       "conflicts": sorted(conflicts)})
    return issues, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", nargs="+", type=Path, help="两份独立填写 CSV，或已有 JSONL")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, help="可选：写出不含答案和引文的仲裁状态 JSONL")
    args = parser.parse_args()
    try:
        issues, report = validate(args.annotations, args.tasks, args.manifest)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"输入无效：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    rendered = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    for issue in issues:
        print(issue, file=sys.stderr)
    if issues:
        return 1
    if any(row["status"] == "pending_adjudication" for row in report):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
