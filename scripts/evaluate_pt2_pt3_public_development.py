"""Rebuild isolated PT7/PT8/PT10/PT11 CC BY development audits without models."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail import qa
from papertrail.qa import _validate_quote, ask
from papertrail.s1_index import index_selection, open_database

GROUPS = ("pt7", "pt8", "pt10", "pt11")
DATE = "20261023"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _gold_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _empty_type() -> dict[str, Any]:
    return {
        "questions": 0,
        "answerable_questions": 0,
        "gold_evidence_slots": 0,
        "qa_candidate_page_slots": 0,
        "qa_candidate_gold_phrase_chunks": 0,
        "extractive_candidate_gold_phrase_slots": 0,
        "quote_validated_gold_phrase_slots": 0,
        "quote_validation_rejected_gold_phrase_slots": 0,
        "paper_quote_limit_skipped_gold_phrase_slots": 0,
        "citation_limit_truncated_gold_phrase_slots": 0,
        "gold_quotes_on_registered_pdf_pages": 0,
        "gold_quotes_in_indexed_chunks": 0,
        "cited_gold_page_slots": 0,
        "citation_contains_gold_phrase_slots": 0,
        "exact_gold_quote_slots": 0,
        "citation_chunk_metadata_valid": 0,
        "citation_quote_in_indexed_chunk": 0,
        "citation_source_validation_failures": 0,
        "unanswerable_questions": 0,
        "unanswerable_with_extractive_candidates": 0,
    }


def _evaluate_group(group: str, temp_root: Path, qa_mode: str) -> dict[str, Any]:
    source_manifest_path = ROOT / "evals" / f"{group}-public-source-manifest-{DATE}.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if (source_manifest.get("dataset_role") != "development"
            or source_manifest.get("license") != "CC BY 4.0"):
        raise ValueError(f"{group}: source manifest is not development data")
    fixture_root = (ROOT / "evals" / "fixtures" / f"{group}-development").resolve()
    sources = source_manifest.get("sources", [])
    if not sources:
        raise ValueError(f"{group}: public source manifest has no sources")
    for source in sources:
        if source.get("benchmark_role") != "development":
            raise ValueError(f"{group}: source is outside the approved CC BY development scope")
        pdf = (ROOT / source["local_pdf"]).resolve()
        if pdf.parent != fixture_root or _sha256(pdf) != source.get("local_pdf_sha256"):
            raise ValueError(f"{group}: source path or SHA-256 mismatch")

    gold_path = ROOT / source_manifest["gold_file"]
    if _sha256(gold_path) != source_manifest.get("gold_sha256"):
        raise ValueError(f"{group}: frozen development gold SHA-256 mismatch")
    rows = _gold_rows(gold_path)
    if len(rows) != source_manifest.get("question_count"):
        raise ValueError(f"{group}: development question count mismatch")

    root_id = f"{group}_development"
    source_by_sha = {source["local_pdf_sha256"]: (ROOT / source["local_pdf"]).resolve()
                     for source in sources}
    config = temp_root / f"{group}-sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": root_id, "path": str(fixture_root)}]}),
                      encoding="utf-8")
    selection = temp_root / f"{group}-selection.jsonl"
    selection.write_text("".join(json.dumps({
        "root_id": root_id,
        "file_name": Path(source["local_pdf"]).name,
        "relative_path": Path(source["local_pdf"]).name,
        "sha256": source["local_pdf_sha256"],
        "kind": "pdf",
        "source_type": "original_pdf",
    }) + "\n" for source in sources), encoding="utf-8")
    database = temp_root / f"{group}.sqlite3"
    index_result = index_selection(database, config, selection, reconcile=True)
    if index_result["added"] != len(sources):
        raise ValueError(f"{group}: fresh public-only index did not include every registered PDF")

    by_type: dict[str, dict[str, Any]] = {}
    by_question: list[dict[str, Any]] = []
    conn = open_database(database, readonly=True)
    for question_index, item in enumerate(rows, start=1):
        question_type = item["question_type"]
        stats = by_type.setdefault(question_type, _empty_type())
        stats["questions"] += 1
        result = ask(database, item["question"], limit=5, mode=qa_mode, generate=False)
        trace = result["retrieval_trace"]
        if (trace["retrieval_mode"] != qa_mode or not trace["index_revision_consistent"]
                or len(trace["query_hash"]) != 64):
            raise ValueError(f"{group} question {question_index}: inconsistent QA retrieval trace")
        stored_trace = conn.execute(
            "SELECT retrieval_json,evidence_json,run_json FROM qa_trajectories WHERE turn_id=?",
            (result["turn_id"],)).fetchone()
        if not stored_trace:
            raise ValueError(f"{group} question {question_index}: QA trajectory missing")
        stored_candidates = json.loads(stored_trace["retrieval_json"])
        stored_citations = json.loads(stored_trace["evidence_json"])
        trace_matches = json.loads(stored_trace["run_json"]) == trace
        candidates_match = ([row["chunk_id"] for row in stored_candidates]
                            == trace["candidate_chunk_ids"])
        citations_match = (list(dict.fromkeys(row["chunk_id"] for row in stored_citations))
                           == trace["citation_chunk_ids"])
        if not (trace_matches and candidates_match and citations_match):
            conn.close()
            raise ValueError(f"{group} question {question_index}: QA trace mismatch "
                             f"({trace_matches},{candidates_match},{citations_match}); "
                             f"stored citations={len(stored_citations)}, "
                             f"reported citations={len(trace['citation_chunk_ids'])}")
        candidate_rows = []
        candidate_ids = trace["candidate_chunk_ids"]
        stage_ids = {
            "extractive_candidate_chunk_ids": trace["extractive_candidate_chunk_ids"],
            "quote_validated_chunk_ids": trace["quote_validated_chunk_ids"],
            "quote_validation_rejected_chunk_ids": trace["quote_validation_rejected_chunk_ids"],
            "paper_quote_limit_skipped_chunk_ids": trace["paper_quote_limit_skipped_chunk_ids"],
            "duplicate_quote_skipped_chunk_ids": trace["duplicate_quote_skipped_chunk_ids"],
            "citation_limit_truncated_chunk_ids": trace["citation_limit_truncated_chunk_ids"],
        }
        sentence_candidate_ids = set(stage_ids["extractive_candidate_chunk_ids"])
        if any(not set(ids).issubset(candidate_ids) for ids in stage_ids.values()) or any(
                not set(ids).issubset(sentence_candidate_ids)
                for name, ids in stage_ids.items() if name != "extractive_candidate_chunk_ids"):
            raise ValueError(f"{group} question {question_index}: QA citation stage escaped candidate pool")
        if candidate_ids:
            marks = ",".join("?" for _ in candidate_ids)
            candidate_rows = conn.execute(
                f"SELECT c.chunk_id,c.page_number,c.body,v.sha256 FROM chunks c "
                f"JOIN paper_versions v USING(version_id) WHERE c.chunk_id IN ({marks})",
                candidate_ids).fetchall()
        question_stats: dict[str, Any] = {
            "question_index": question_index,
            "question_type": question_type,
            "answerable": not item["abstain"],
            "gold_evidence_slots": len(item["evidence"]),
            "extractive_citation_count": len(result["claims"]),
            "retrieval_mode": trace["retrieval_mode"],
            "index_revision": trace["index_revision"],
            "index_revision_consistent": trace["index_revision_consistent"],
            "query_hash": trace["query_hash"],
            "candidate_chunk_ids": candidate_ids,
            **stage_ids,
            "citation_chunk_ids": trace["citation_chunk_ids"],
            "qa_candidate_page_slots": 0,
            "qa_candidate_gold_phrase_chunks": 0,
            "extractive_candidate_gold_phrase_slots": 0,
            "quote_validated_gold_phrase_slots": 0,
            "quote_validation_rejected_gold_phrase_slots": 0,
            "paper_quote_limit_skipped_gold_phrase_slots": 0,
            "citation_limit_truncated_gold_phrase_slots": 0,
            "gold_quotes_on_registered_pdf_pages": 0,
            "gold_quotes_in_indexed_chunks": 0,
            "cited_gold_page_slots": 0,
            "citation_contains_gold_phrase_slots": 0,
            "exact_gold_quote_slots": 0,
            "citation_source_validation_failures": 0,
        }
        by_question.append(question_stats)
        if item["abstain"]:
            stats["unanswerable_questions"] += 1
            stats["unanswerable_with_extractive_candidates"] += int(bool(result["claims"]))
            continue

        stats["answerable_questions"] += 1
        evidence = item["evidence"]
        stats["gold_evidence_slots"] += len(evidence)
        candidate_pages = {(row["sha256"], row["page_number"]) for row in candidate_rows}
        candidate_page_slots = sum((slot["sha256"], slot["pdf_page"]) in candidate_pages
                                   for slot in evidence)
        candidate_phrase_rows = [
            [row for row in candidate_rows
             if row["sha256"] == slot["sha256"] and row["page_number"] == slot["pdf_page"]
             and _normalize(slot["quote"]) in _normalize(row["body"])]
            for slot in evidence]
        candidate_phrase_chunks = sum(bool(rows) for rows in candidate_phrase_rows)
        extractive_phrase_slots = sum(any(
            row["chunk_id"] in set(stage_ids["extractive_candidate_chunk_ids"])
            for row in rows) for rows in candidate_phrase_rows)
        validated_phrase_slots = sum(any(
            row["chunk_id"] in set(stage_ids["quote_validated_chunk_ids"])
            for row in rows) for rows in candidate_phrase_rows)
        rejected_phrase_slots = sum(any(
            row["chunk_id"] in set(stage_ids["quote_validation_rejected_chunk_ids"])
            for row in rows) for rows in candidate_phrase_rows)
        paper_limit_phrase_slots = sum(any(
            row["chunk_id"] in set(stage_ids["paper_quote_limit_skipped_chunk_ids"])
            for row in rows) for rows in candidate_phrase_rows)
        citation_limit_phrase_slots = sum(any(
            row["chunk_id"] in set(stage_ids["citation_limit_truncated_chunk_ids"])
            for row in rows) for rows in candidate_phrase_rows)
        stats["qa_candidate_page_slots"] += candidate_page_slots
        stats["qa_candidate_gold_phrase_chunks"] += candidate_phrase_chunks
        stats["extractive_candidate_gold_phrase_slots"] += extractive_phrase_slots
        stats["quote_validated_gold_phrase_slots"] += validated_phrase_slots
        stats["quote_validation_rejected_gold_phrase_slots"] += rejected_phrase_slots
        stats["paper_quote_limit_skipped_gold_phrase_slots"] += paper_limit_phrase_slots
        stats["citation_limit_truncated_gold_phrase_slots"] += citation_limit_phrase_slots
        question_stats["qa_candidate_page_slots"] = candidate_page_slots
        question_stats["qa_candidate_gold_phrase_chunks"] = candidate_phrase_chunks
        question_stats["extractive_candidate_gold_phrase_slots"] = extractive_phrase_slots
        question_stats["quote_validated_gold_phrase_slots"] = validated_phrase_slots
        question_stats["quote_validation_rejected_gold_phrase_slots"] = rejected_phrase_slots
        question_stats["paper_quote_limit_skipped_gold_phrase_slots"] = paper_limit_phrase_slots
        question_stats["citation_limit_truncated_gold_phrase_slots"] = citation_limit_phrase_slots

        citations = [claim["evidence"] for claim in result["claims"]]
        for slot in evidence:
            source_pdf = source_by_sha[slot["sha256"]]
            valid_page_quote = int(_validate_quote(
                str(source_pdf), slot["sha256"], slot["pdf_page"], slot["quote"], {}))
            stats["gold_quotes_on_registered_pdf_pages"] += valid_page_quote
            question_stats["gold_quotes_on_registered_pdf_pages"] += valid_page_quote
            indexed_chunks = conn.execute(
                "SELECT c.body FROM chunks c JOIN paper_versions v USING(version_id) "
                "WHERE v.sha256=? AND c.page_number=?",
                (slot["sha256"], slot["pdf_page"])).fetchall()
            indexed_quote = int(any(
                _normalize(slot["quote"]) in _normalize(chunk["body"])
                for chunk in indexed_chunks))
            stats["gold_quotes_in_indexed_chunks"] += indexed_quote
            question_stats["gold_quotes_in_indexed_chunks"] += indexed_quote
            matching = [citation for citation in citations
                        if citation.get("sha256") == slot["sha256"]
                        and citation.get("pdf_page") == slot["pdf_page"]]
            cited_page = int(bool(matching))
            stats["cited_gold_page_slots"] += cited_page
            question_stats["cited_gold_page_slots"] += cited_page
            target_quote = _normalize(slot["quote"])
            contains_phrase = int(any(
                target_quote in _normalize(citation.get("quote", "")) for citation in matching))
            exact_quote = int(any(
                target_quote == _normalize(citation.get("quote", "")) for citation in matching))
            stats["citation_contains_gold_phrase_slots"] += contains_phrase
            question_stats["citation_contains_gold_phrase_slots"] += contains_phrase
            stats["exact_gold_quote_slots"] += exact_quote
            question_stats["exact_gold_quote_slots"] += exact_quote

        for citation in citations:
            citation_row = conn.execute(
                "SELECT c.page_number,c.body,v.sha256,l.absolute_path "
                "FROM chunks c JOIN paper_versions v USING(version_id) "
                "JOIN source_locations l USING(version_id) WHERE c.chunk_id=?",
                (citation.get("chunk_id"),)).fetchone()
            metadata_valid = bool(citation_row and citation_row["sha256"] == citation.get("sha256")
                                  and citation_row["page_number"] == citation.get("pdf_page")
                                  and citation_row["absolute_path"] == citation.get("path"))
            chunk_quote_valid = bool(metadata_valid and
                _normalize(citation.get("quote", "")) in _normalize(citation_row["body"]))
            source_valid = bool(metadata_valid and _validate_quote(
                citation["path"], citation["sha256"], citation["pdf_page"], citation["quote"], {}))
            stats["citation_chunk_metadata_valid"] += int(metadata_valid)
            stats["citation_quote_in_indexed_chunk"] += int(chunk_quote_valid)
            stats["citation_source_validation_failures"] += int(not source_valid)
            question_stats["citation_source_validation_failures"] += int(not source_valid)

    conn.close()

    return {
        "group_id": source_manifest["group_id"],
        "source_manifest_sha256": _sha256(source_manifest_path),
        "gold_sha256": _sha256(gold_path),
        "question_count": len(rows),
            "indexed_public_pdfs": index_result["added"],
        "by_question_type": by_type,
        "by_question": by_question,
    }


def run(output: Path | None = None, qa_mode: str = "bm25") -> dict[str, Any]:
    if qa_mode not in {"bm25", "bm25_expanded"}:
        raise ValueError("public development audit supports only offline BM25 modes")
    def reject_model_call(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("public development diagnostic must not call a model")

    original_chat_json = qa.chat_json
    qa.chat_json = reject_model_call
    try:
        with tempfile.TemporaryDirectory(prefix="papertrail-pt2-pt3-public-dev-") as temporary:
            groups = [_evaluate_group(group, Path(temporary), qa_mode) for group in GROUPS]
    finally:
        qa.chat_json = original_chat_json

    report = {
        "schema_version": 4,
        "dataset_role": "development_diagnostic",
        "scope": {
            "groups": list(GROUPS),
            "source_license": "CC BY 4.0",
            "fresh_temporary_indexes": True,
            "model_calls": 0,
            "cost_usd_estimate": 0,
            "extractive_qa_mode": qa_mode,
        },
        "groups": groups,
        "refusal_quality": {
            "status": "not_assessed_without_generation",
            "unanswerable_candidate_metric": "candidate presence only; not a wrong-refusal or correct-refusal score",
        },
        "citation_quality": {
            "gold_phrase_containment": "page and normalized gold phrase checked against extractive citation",
            "semantic_support": "not assessed without generation or human review",
        },
        "answer_correctness": {
            "status": "not_assessed_without_generation_or_human_review",
        },
        "limitations": [
            "只读取 PT7/PT8/PT10/PT11 已登记的 CC BY 4.0 开发集；不触碰其他数据组。",
            "候选完整覆盖是页级检索指标，不等于答案正确或引用支持。",
            "不可答题候选不等于错误拒答；无模型运行不能评估真实拒答质量。",
            "开发集已见，不是盲测；未修改冻结 gold。",
        ],
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(
        "evals/pt2-pt3-public-qa-candidate-audit-20261115.json"))
    parser.add_argument("--qa-mode", choices=("bm25", "bm25_expanded"), default="bm25")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report = run(output, args.qa_mode)
    print(json.dumps({"output": str(output), "scope": report["scope"],
                      "groups": [{"group_id": group["group_id"],
                                  "by_question_type": group["by_question_type"]}
                                 for group in report["groups"]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
