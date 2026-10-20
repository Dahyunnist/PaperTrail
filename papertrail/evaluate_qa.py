"""Compare extractive and model-reviewed QA on a frozen local gold set."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import statistics
from pathlib import Path
from typing import Any

from .gold import load_gold
from .qa import ask
from .s1_index import open_database


def _copy_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def _usage_snapshot() -> tuple[int, float, int, int]:
    path = Path(os.environ.get("PAPERTRAIL_LLM_BUDGET_FILE", ".local/p6-api-usage.json"))
    if not path.exists():
        return 0, 0.0, 0, 0
    data = json.loads(path.read_text(encoding="utf-8"))
    return (len(data.get("requests", [])), float(data.get("spent_upper_bound_usd", 0.0)),
            sum(int(row.get("prompt_tokens") or 0) for row in data.get("requests", [])),
            sum(int(row.get("completion_tokens") or 0) for row in data.get("requests", [])))


def _gold_page_coverage(expected_pages: set[tuple[str, int]], citations: list[dict[str, Any]]) -> dict[str, Any]:
    cited_pages = {(item.get("sha256"), item.get("page")) for item in citations}
    covered_pages = expected_pages & cited_pages
    return {"covered_pages": len(covered_pages), "expected_pages": len(expected_pages),
            "coverage": len(covered_pages) / len(expected_pages) if expected_pages else None,
            "all_expected_pages_cited": bool(expected_pages) and expected_pages.issubset(cited_pages)}


def _run_mode(database: Path, items: list[dict[str, Any]], mode: str,
              model: bool, artifact: Path | None = None, limit: int = 5) -> dict[str, Any]:
    if model and not os.environ.get("PAPERTRAIL_LLM_MODEL"):
        raise ValueError("model run requires PAPERTRAIL_LLM_MODEL")
    cases = []
    for item in items:
        request_count_before, cost_before, prompt_before, completion_before = _usage_snapshot()
        result = ask(database, item["question"], conversation_id=f"p6-{mode}-{item['id']}",
                     limit=limit, mode=mode, generate=model, artifact=artifact)
        request_count_after, cost_after, prompt_after, completion_after = _usage_snapshot()
        request_count = request_count_after - request_count_before
        ledger_cost = round(cost_after - cost_before, 8)
        if request_count:
            result["usage"] = {**(result.get("usage") or {}), "estimated_usd": ledger_cost,
                               "request_count": request_count,
                               "prompt_eval_count": prompt_after - prompt_before,
                               "eval_count": completion_after - completion_before}
        citations = []
        for claim in result["claims"]:
            for ref in claim.get("support_evidence") or [claim.get("evidence", {})]:
                citations.append({"sha256": ref.get("sha256"), "page": ref.get("pdf_page"),
                                  "quote": ref.get("quote"), "claim": claim["text"]})
        expected_pages = {(row["sha256"], row["pdf_page"]) for row in item["evidence"]}
        cited_pages = {(ref["sha256"], ref["page"]) for ref in citations}
        page_coverage = _gold_page_coverage(expected_pages, citations)
        trace = open_database(database)
        try:
            rejected = trace.execute("SELECT rejected_claims FROM qa_trajectories WHERE turn_id=?",
                                     (result["turn_id"],)).fetchone()[0]
        finally:
            trace.close()
        cases.append({"id": item["id"], "type": item["question_type"], "question": item["question"],
                      "expected_answer": item["expected_answer"], "abstain_expected": item["abstain"],
                      "status": result["status"], "answered": bool(result["claims"]),
                      "coverage_complete": result.get("coverage_complete"),
                      "diagnostics": (result.get("usage") or {}).get("_diagnostics", {}),
                      "expected_page_cited": bool(expected_pages & cited_pages),
                      "expected_pages_cited": page_coverage["covered_pages"],
                      "expected_page_count": page_coverage["expected_pages"],
                      "expected_page_coverage": page_coverage["coverage"],
                      "all_expected_pages_cited": page_coverage["all_expected_pages_cited"],
                      "citations": citations, "claims": [row["text"] for row in result["claims"]],
                      "rejected_claims": rejected, "latency_ms": result["latency_ms"],
                      "usage": result["usage"], "answer": result["answer"]})
    answerable = [row for row in cases if not row["abstain_expected"]]
    unanswerable = [row for row in cases if row["abstain_expected"]]
    latencies = [row["latency_ms"] for row in cases]
    usage_rows = [row["usage"] for row in cases if row["usage"]]
    total_cost = sum(float(row.get("estimated_usd") or 0) for row in usage_rows)
    by_type = {}
    for kind in sorted({row["type"] for row in cases}):
        group = [row for row in cases if row["type"] == kind]
        group_answerable = [row for row in group if not row["abstain_expected"]]
        group_unanswerable = [row for row in group if row["abstain_expected"]]
        by_type[kind] = {"total": len(group),
                         "answerable_coverage": (sum(row["answered"] for row in group_answerable) / len(group_answerable)
                                                 if group_answerable else None),
                         "gold_page_citation_rate": (sum(row["expected_page_cited"] for row in group_answerable) / len(group_answerable)
                                                     if group_answerable else None),
                         "all_expected_pages_cited_rate": (sum(row["all_expected_pages_cited"] for row in group_answerable) / len(group_answerable)
                                                           if group_answerable else None),
                         "correct_abstention_rate": (sum(not row["answered"] for row in group_unanswerable) / len(group_unanswerable)
                                                     if group_unanswerable else None)}
    citations = [citation for row in answerable for citation in row["citations"]]
    gold_pages_by_id = {item["id"]: {(e["sha256"], e["pdf_page"]) for e in item["evidence"]} for item in items}
    matching_citations = sum((citation["sha256"], citation["page"]) in gold_pages_by_id[row["id"]]
                             for row in answerable for citation in row["citations"])
    reviewed_claims = sum(len(row["claims"]) + row["rejected_claims"] for row in cases)
    accepted_claims = sum(len(row["claims"]) for row in cases)
    return {"model_run": model, "questions": len(cases),
            "answerable_coverage": sum(row["answered"] for row in answerable) / len(answerable) if answerable else None,
            "complete_answer_rate": (sum(row["coverage_complete"] is True for row in answerable) / len(answerable)
                                     if model and answerable else None),
            "partial_answer_count": sum(row["status"] == "generated_partial" for row in answerable),
            "gold_page_citation_rate": sum(row["expected_page_cited"] for row in answerable) / len(answerable) if answerable else None,
            "all_expected_pages_cited_rate": (sum(row["all_expected_pages_cited"] for row in answerable) / len(answerable)
                                              if answerable else None),
            "gold_page_coverage": (sum(row["expected_pages_cited"] for row in answerable) /
                                   sum(row["expected_page_count"] for row in answerable)
                                   if sum(row["expected_page_count"] for row in answerable) else None),
            "correct_abstention_rate": sum(not row["answered"] for row in unanswerable) / len(unanswerable) if unanswerable else None,
            "false_answer_rate": sum(row["answered"] for row in unanswerable) / len(unanswerable) if unanswerable else None,
            "mean_latency_ms": statistics.mean(latencies) if latencies else 0,
            "median_latency_ms": statistics.median(latencies) if latencies else 0,
            "citation_precision_at_gold_pages": matching_citations / len(citations) if citations else 0,
            "claim_support_acceptance_rate": accepted_claims / reviewed_claims if reviewed_claims else None,
            "reviewed_claims": reviewed_claims, "rejected_claims": reviewed_claims - accepted_claims,
            "by_question_type": by_type,
            "api_requests": sum(int((row["usage"] or {}).get("request_count") or 0) for row in cases),
            "prompt_tokens": sum(int(row.get("prompt_eval_count") or 0) for row in usage_rows),
            "completion_tokens": sum(int(row.get("eval_count") or 0) for row in usage_rows),
            "cost_upper_bound_usd": round(total_cost, 8), "cases": cases}


def compare_qa(database: Path, gold_path: Path, output: Path, mode: str = "bm25",
               artifact: Path | None = None, limit: int = 5,
               minimum_questions: int = 30) -> dict[str, Any]:
    items = (load_gold(gold_path, minimum_questions=minimum_questions)
             if minimum_questions != 30 else load_gold(gold_path))
    baseline_db = output.with_name(output.stem + "-extractive.sqlite3")
    model_db = output.with_name(output.stem + "-model.sqlite3")
    _copy_database(database, baseline_db)
    _copy_database(database, model_db)
    configured_model = os.environ.get("PAPERTRAIL_LLM_MODEL")
    configured_provider = os.environ.get("PAPERTRAIL_LLM_PROVIDER")
    try:
        baseline = _run_mode(baseline_db, items, mode, False, artifact, limit)
        if configured_model:
            os.environ["PAPERTRAIL_LLM_MODEL"] = configured_model
        if configured_provider:
            os.environ["PAPERTRAIL_LLM_PROVIDER"] = configured_provider
        model = _run_mode(model_db, items, mode, True, artifact, limit)
    finally:
        if configured_model is None:
            os.environ.pop("PAPERTRAIL_LLM_MODEL", None)
        else:
            os.environ["PAPERTRAIL_LLM_MODEL"] = configured_model
        if configured_provider is None:
            os.environ.pop("PAPERTRAIL_LLM_PROVIDER", None)
        else:
            os.environ["PAPERTRAIL_LLM_PROVIDER"] = configured_provider
    result = {"gold": str(gold_path.name), "mode": mode, "extractive": baseline, "model_reviewed": model}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--gold", type=Path, default=Path("evals/p6-gold-20261020.jsonl"))
    parser.add_argument("--out", type=Path, default=Path(".local/p6-qa-comparison.json"))
    parser.add_argument("--mode", default="bm25")
    parser.add_argument("--vector-artifact", type=Path)
    parser.add_argument("--limit", type=int, default=5, help="每题最多组织的证据摘录数（1–8）")
    parser.add_argument("--minimum-questions", type=int, default=30)
    args = parser.parse_args()
    result = compare_qa(args.db, args.gold, args.out, args.mode, args.vector_artifact,
                        args.limit, args.minimum_questions)
    print(json.dumps({key: {k: v for k, v in value.items() if k != "cases"}
                      for key, value in result.items() if isinstance(value, dict)}, indent=2))


if __name__ == "__main__":
    main()
