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
from papertrail.retrieval import retrieve
from papertrail.s1_index import index_selection, open_database

GROUPS = ("pt7", "pt8", "pt10", "pt11")
DATE = "20261023"
DEPTHS = (20, 40, 80)


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
        "complete_questions_at_depth": {str(depth): 0 for depth in DEPTHS},
        "retrieved_evidence_slots_at_depth": {str(depth): 0 for depth in DEPTHS},
        "retrieved_gold_phrase_chunks_at_depth": {str(depth): 0 for depth in DEPTHS},
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


def _evaluate_group(group: str, temp_root: Path) -> dict[str, Any]:
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
    conn = open_database(database, readonly=True)
    for item in rows:
        question_type = item["question_type"]
        stats = by_type.setdefault(question_type, _empty_type())
        stats["questions"] += 1
        result = ask(database, item["question"], limit=5, mode="bm25", generate=False)
        if item["abstain"]:
            stats["unanswerable_questions"] += 1
            stats["unanswerable_with_extractive_candidates"] += int(bool(result["claims"]))
            continue

        stats["answerable_questions"] += 1
        evidence = item["evidence"]
        stats["gold_evidence_slots"] += len(evidence)
        for depth in DEPTHS:
            candidates = retrieve(database, item["question"], depth,
                                  source_type="original_pdf", mode="bm25_expanded")
            pages = {(candidate["sha256"], candidate["pdf_page"]) for candidate in candidates}
            target_pages = {(slot["sha256"], slot["pdf_page"]) for slot in evidence}
            stats["complete_questions_at_depth"][str(depth)] += int(target_pages <= pages)
            stats["retrieved_evidence_slots_at_depth"][str(depth)] += sum(
                (slot["sha256"], slot["pdf_page"]) in pages for slot in evidence)
            stats["retrieved_gold_phrase_chunks_at_depth"][str(depth)] += sum(
                any(candidate["sha256"] == slot["sha256"]
                    and candidate["pdf_page"] == slot["pdf_page"]
                    and _normalize(slot["quote"]) in _normalize(candidate["text"])
                    for candidate in candidates) for slot in evidence)

        citations = [claim["evidence"] for claim in result["claims"]]
        for slot in evidence:
            source_pdf = source_by_sha[slot["sha256"]]
            stats["gold_quotes_on_registered_pdf_pages"] += int(_validate_quote(
                str(source_pdf), slot["sha256"], slot["pdf_page"], slot["quote"], {}))
            indexed_chunks = conn.execute(
                "SELECT c.body FROM chunks c JOIN paper_versions v USING(version_id) "
                "WHERE v.sha256=? AND c.page_number=?",
                (slot["sha256"], slot["pdf_page"])).fetchall()
            stats["gold_quotes_in_indexed_chunks"] += int(any(
                _normalize(slot["quote"]) in _normalize(chunk["body"])
                for chunk in indexed_chunks))
            matching = [citation for citation in citations
                        if citation.get("sha256") == slot["sha256"]
                        and citation.get("pdf_page") == slot["pdf_page"]]
            stats["cited_gold_page_slots"] += int(bool(matching))
            target_quote = _normalize(slot["quote"])
            stats["citation_contains_gold_phrase_slots"] += int(any(
                target_quote in _normalize(citation.get("quote", "")) for citation in matching))
            stats["exact_gold_quote_slots"] += int(any(
                target_quote == _normalize(citation.get("quote", "")) for citation in matching))

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

    conn.close()

    return {
        "group_id": source_manifest["group_id"],
        "source_manifest_sha256": _sha256(source_manifest_path),
        "gold_sha256": _sha256(gold_path),
        "question_count": len(rows),
            "indexed_public_pdfs": index_result["added"],
        "by_question_type": by_type,
    }


def run(output: Path | None = None) -> dict[str, Any]:
    def reject_model_call(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("public development diagnostic must not call a model")

    original_chat_json = qa.chat_json
    qa.chat_json = reject_model_call
    try:
        with tempfile.TemporaryDirectory(prefix="papertrail-pt2-pt3-public-dev-") as temporary:
            groups = [_evaluate_group(group, Path(temporary)) for group in GROUPS]
    finally:
        qa.chat_json = original_chat_json

    report = {
        "schema_version": 1,
        "dataset_role": "development_diagnostic",
        "scope": {
            "groups": list(GROUPS),
            "source_license": "CC BY 4.0",
            "fresh_temporary_indexes": True,
            "model_calls": 0,
            "cost_usd_estimate": 0,
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
        "evals/pt2-pt3-public-development-diagnostic-20261115.json"))
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report = run(output)
    print(json.dumps({"output": str(output), "scope": report["scope"],
                      "groups": [{"group_id": group["group_id"],
                                  "by_question_type": group["by_question_type"]}
                                 for group in report["groups"]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
