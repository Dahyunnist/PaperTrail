"""Validate annotated PT-1 CSV, export v2 JSONL, and import runtime gold in one step."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import import_pt1_gold_jsonl
import validate_pt1_gold_jsonl

CSV_FIELDS = {
    "task_id", "paper_split", "doi", "pdf_sha256", "candidate_question", "question_type",
    "answerability", "expected_answer", "minimal_complete_evidence_quote", "evidence_pdf_pages",
    "original_pdf_excerpt", "span_start_char", "span_end_char", "annotator", "reviewer",
    "review_status", "notes",
}
TYPES = {"fact_location", "method_comparison", "cross_paper", "multi_hop", "conflict", "unanswerable"}
ANSWERABILITY = {"可答": "answerable", "不可答": "unanswerable"}


def _list_value(raw: str, field: str) -> list[Any]:
    value = raw.strip()
    if not value:
        raise ValueError(f"{field} is required")
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must be a JSON array when multiple values are used") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"{field} must be a JSON array")
        return parsed
    return [value]


def _integer_list(raw: str, field: str) -> list[int]:
    values = _list_value(raw, field)
    result = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError(f"{field} must contain integer PDF page numbers")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must contain integer PDF page numbers") from exc
        if str(number) != str(value).strip() and not isinstance(value, int):
            raise ValueError(f"{field} must contain integer PDF page numbers")
        result.append(number)
    return result


def _span_list(row: dict[str, str], count: int) -> list[dict[str, int]]:
    if count == 1:
        try:
            start, end = int(row["span_start_char"]), int(row["span_end_char"])
        except (TypeError, ValueError) as exc:
            raise ValueError("span_start_char and span_end_char must be filled") from exc
        return [{"start_char": start, "end_char": end}]
    try:
        notes = json.loads(row["notes"])
    except json.JSONDecodeError as exc:
        raise ValueError("multiple citations need notes as JSON with a spans array") from exc
    spans = notes.get("spans") if isinstance(notes, dict) else notes
    if not isinstance(spans, list) or len(spans) != count:
        raise ValueError("notes spans count must match quote/page count")
    result = []
    for span in spans:
        if not isinstance(span, dict) or set(span) != {"start_char", "end_char"}:
            raise ValueError("each notes span needs start_char and end_char")
        if any(not isinstance(span[key], int) or isinstance(span[key], bool) for key in span):
            raise ValueError("notes span offsets must be integers")
        result.append(span)
    return result


def export_csv_rows(csv_path: Path, manifest_path: Path = validate_pt1_gold_jsonl.DEFAULT_MANIFEST) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {item["doi"]: item for item in manifest["sources"]}
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not CSV_FIELDS.issubset(reader.fieldnames or []):
                raise ValueError("CSV is missing required PT1 annotation columns")
            rows = list(reader)
    except OSError as exc:
        raise ValueError(f"cannot read annotation CSV ({type(exc).__name__})") from exc
    if not rows:
        raise ValueError("annotation CSV has no rows")
    ids: set[str] = set()
    for row_number, row in enumerate(rows, 2):
        raw_task_id = row.get("task_id")
        task_id = raw_task_id.strip() if isinstance(raw_task_id, str) and raw_task_id.strip() else f"row-{row_number}"
        try:
            if any(row.get(field) is None for field in CSV_FIELDS):
                raise ValueError("CSV row has missing cells")
            if task_id in ids:
                raise ValueError("task_id is duplicated")
            ids.add(task_id)
            source = sources.get(row["doi"].strip())
            if source is None:
                raise ValueError("DOI is absent from the frozen manifest")
            if row["paper_split"] != "development_seen" or row["pdf_sha256"].lower() != source["pdf_sha256"]:
                raise ValueError("paper split or PDF SHA-256 does not match the frozen manifest")
            if not row["candidate_question"].strip() or not row["expected_answer"].strip():
                raise ValueError("question and expected_answer must be filled")
            if row["review_status"].strip() != "通过":
                raise ValueError("review_status must be 通过")
            if not row["annotator"].strip() or not row["reviewer"].strip() or row["annotator"].strip() == row["reviewer"].strip():
                raise ValueError("annotator and reviewer must be present and different")
            qtype = row["question_type"].strip()
            if qtype not in TYPES:
                raise ValueError("question_type is missing or invalid")
            answerability = ANSWERABILITY.get(row["answerability"].strip())
            if answerability is None:
                raise ValueError("answerability must be 可答 or 不可答; resolve 歧义 before export")
            if (answerability == "unanswerable") != (qtype == "unanswerable"):
                raise ValueError("question_type must be unanswerable exactly when answerability is 不可答")

            citations: list[dict[str, Any]] = []
            evidence_fields = ("minimal_complete_evidence_quote", "evidence_pdf_pages", "original_pdf_excerpt",
                               "span_start_char", "span_end_char")
            if answerability == "unanswerable":
                if any(row[field].strip() for field in evidence_fields):
                    raise ValueError("unanswerable rows must have empty evidence fields")
            else:
                quotes = _list_value(row["minimal_complete_evidence_quote"], "minimal_complete_evidence_quote")
                pages = _integer_list(row["evidence_pdf_pages"], "evidence_pdf_pages")
                excerpts = _list_value(row["original_pdf_excerpt"], "original_pdf_excerpt")
                if not (len(quotes) == len(pages) == len(excerpts)):
                    raise ValueError("quote, page, and excerpt counts must match")
                if any(not isinstance(value, str) or not value for value in quotes + excerpts):
                    raise ValueError("quotes and excerpts must be nonempty strings")
                spans = _span_list(row, len(quotes))
                pdf_path = (validate_pt1_gold_jsonl.ROOT / source["local_pdf"]).resolve()
                if validate_pt1_gold_jsonl.ROOT.resolve() not in pdf_path.parents:
                    raise ValueError("manifest PDF path escapes repository")
                import pymupdf
                with pymupdf.open(pdf_path) as document:
                    for quote, page_number, excerpt, span in zip(quotes, pages, excerpts, spans):
                        if not 1 <= page_number <= document.page_count:
                            raise ValueError("evidence_pdf_pages is outside the source PDF")
                        page_text = document[page_number - 1].get_text("text")
                        start, end = span["start_char"], span["end_char"]
                        if start < 0 or end <= start or end > len(page_text) or page_text[start:end] != quote:
                            raise ValueError("quote span does not exactly match source PDF page text")
                        if excerpt not in page_text or quote not in excerpt:
                            raise ValueError("original_pdf_excerpt must be exact page text containing the quote")
                        citations.append({
                            "doi": source["doi"], "pdf_sha256": source["pdf_sha256"],
                            "pdf_page": page_number, "start_char": start, "end_char": end,
                            "quote": quote, "relation": "supports",
                        })

            if qtype in {"cross_paper", "method_comparison", "multi_hop", "conflict"}:
                raise ValueError("this CSV task is single-paper; multi-paper question types need curated v2 JSONL")
            records.append({
                "id": task_id, "paper_ids": [source["doi"]], "split": "development",
                "question_type": qtype, "question": row["candidate_question"].strip(),
                "expected_answer": row["expected_answer"].strip(), "answerability": answerability,
                "evidence": citations, "minimumCompleteEvidenceSet": True,
                "annotation_status": "human_verified", "annotator": row["annotator"].strip(),
                "reviewer": row["reviewer"].strip(),
            })
        except (KeyError, ValueError, TypeError, OSError, RuntimeError) as exc:
            errors.append(f"CSV row {row_number} ({task_id}): {exc}")
    if errors:
        raise ValueError("CSV annotation validation failed:\n" + "\n".join(errors))
    return records


def import_csv(csv_path: Path, v2_output: Path, runtime_gold_output: Path, sources_output: Path,
               manifest_path: Path = validate_pt1_gold_jsonl.DEFAULT_MANIFEST,
               min_questions: int = 40, min_papers: int = 30) -> tuple[int, int]:
    if min_questions < 1 or min_papers < 1:
        raise ValueError("minimum question and paper counts must be positive")
    resolved_input = csv_path.resolve()
    outputs = {v2_output.resolve(), runtime_gold_output.resolve(), sources_output.resolve()}
    if len(outputs) != 3 or resolved_input in outputs:
        raise ValueError("input and output paths must be distinct")
    rows = export_csv_rows(csv_path, manifest_path)
    v2_output.parent.mkdir(parents=True, exist_ok=True)
    v2_temp = v2_output.with_name(v2_output.name + ".partial")
    try:
        v2_temp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        question_count, quote_count = import_pt1_gold_jsonl.convert(
            v2_temp, runtime_gold_output, sources_output, manifest_path,
            min_questions=min_questions, min_papers=min_papers,
        )
        v2_temp.replace(v2_output)
    finally:
        v2_temp.unlink(missing_ok=True)
    return question_count, quote_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotation_csv", type=Path)
    parser.add_argument("--manifest", type=Path, default=validate_pt1_gold_jsonl.DEFAULT_MANIFEST)
    parser.add_argument("--output-v2", type=Path, required=True)
    parser.add_argument("--output-gold", type=Path, required=True)
    parser.add_argument("--output-sources", type=Path, required=True)
    parser.add_argument("--min-questions", type=int, default=40)
    parser.add_argument("--min-papers", type=int, default=30)
    args = parser.parse_args()
    questions, quotes = import_csv(
        args.annotation_csv, args.output_v2, args.output_gold, args.output_sources,
        args.manifest, args.min_questions, args.min_papers,
    )
    print(f"Imported {questions} reviewed annotations; verified {quotes} PDF quotes.")


if __name__ == "__main__":
    main()
