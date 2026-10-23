"""Run extractive QA diagnostics on the PT7/PT8/PT10/PT11 development groups only."""

from __future__ import annotations

import json
import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.qa import ask
from papertrail.retrieval import retrieve
from papertrail.s1_index import open_database


GROUPS = ("pt7", "pt8", "pt10", "pt11")
DATE = "20261023"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).casefold().strip()


def _gold_rows(group: str) -> list[dict[str, Any]]:
    path = ROOT / "evals" / f"{group}-development-gold-{DATE}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def evaluate_group(group: str) -> dict[str, Any]:
    database = ROOT / ".local" / f"{group}-development.sqlite3"
    artifact = ROOT / ".local" / f"{group}-development.vectors.joblib"
    rows = _gold_rows(group)
    conn = open_database(database)
    question_results = []
    answerable_gold_pages = 0
    parsed_gold_pages = 0
    parsed_gold_quotes = 0
    retrieved_gold_pages = 0
    cited_gold_pages = 0
    exact_quotes = 0
    contained_quotes = 0
    unanswerable_with_excerpts = 0
    try:
        for item in rows:
            if item["abstain"]:
                result = ask(database, item["question"], limit=5, mode="bm25", generate=False,
                             artifact=artifact)
                has_excerpts = bool(result["claims"])
                unanswerable_with_excerpts += int(has_excerpts)
                question_results.append({"id": item["id"], "question_type": item["question_type"], "abstain": True,
                                         "extractive_candidates_returned": has_excerpts})
                continue

            answerable_gold_pages += len(item["evidence"])
            parsed_pages = retrieved_pages = cited_pages = quote_exact = quote_contained_count = 0
            retrieved = retrieve(database, item["question"], 20, source_type="original_pdf",
                                 mode="bm25_expanded")
            retrieved_page_keys = {(row["sha256"], row["pdf_page"]) for row in retrieved}
            result = ask(database, item["question"], limit=5, mode="bm25", generate=False,
                         artifact=artifact)
            citations = [(claim["evidence"]["sha256"], claim["evidence"]["pdf_page"],
                          _normalize(claim["evidence"]["quote"])) for claim in result["claims"]]
            evidence_path = []
            for evidence in item["evidence"]:
                args = (evidence["sha256"], evidence["pdf_page"])
                chunks = conn.execute(
                    "SELECT c.body FROM chunks c JOIN paper_versions v ON v.version_id=c.version_id "
                    "WHERE v.sha256=? AND c.page_number=?", args).fetchall()
                parsed_quote = any(_normalize(evidence["quote"]) in _normalize(chunk["body"])
                                   for chunk in chunks)
                parsed_page = bool(chunks)
                retrieved_page = args in retrieved_page_keys
                page_cited = any(sha == args[0] and page == args[1] for sha, page, _ in citations)
                phrase = _normalize(evidence["quote"])
                quote_equal = any(sha == args[0] and page == args[1] and phrase == quote
                                  for sha, page, quote in citations)
                quote_contained_hit = any(sha == args[0] and page == args[1] and phrase in quote
                                          for sha, page, quote in citations)
                parsed_pages += int(parsed_page)
                parsed_gold_pages += int(parsed_page)
                parsed_gold_quotes += int(parsed_quote)
                retrieved_pages += int(retrieved_page)
                retrieved_gold_pages += int(retrieved_page)
                cited_pages += int(page_cited)
                cited_gold_pages += int(page_cited)
                quote_exact += int(quote_equal)
                exact_quotes += int(quote_equal)
                quote_contained_count += int(quote_contained_hit)
                contained_quotes += int(quote_contained_hit)
                evidence_path.append({
                    "sha256": args[0], "pdf_page": args[1],
                    "parsed_page": parsed_page, "gold_quote_in_parsed_chunks": parsed_quote,
                    "top20_retrieval_rank": next((index + 1 for index, row in enumerate(retrieved)
                                                   if (row["sha256"], row["pdf_page"]) == args), None),
                    "final_page_cited": page_cited, "exact_quote_cited": quote_equal,
                    "gold_phrase_contained": quote_contained_hit,
                    "final_quotes": [quote for sha, page, quote in citations
                                     if sha == args[0] and page == args[1]],
                })
            question_results.append({
                "id": item["id"], "question_type": item["question_type"], "abstain": False,
                "gold_pages": len(item["evidence"]), "parsed_pages": parsed_pages,
                "top20_retrieved_pages": retrieved_pages, "final_cited_pages": cited_pages,
                "exact_quote_citations": quote_exact, "gold_phrase_contained": quote_contained_count,
                "evidence_path": evidence_path,
            })
    finally:
        conn.close()

    return {
        "group_id": f"{group}-public-development-{DATE}",
        "questions": len(rows),
        "answerable_questions": sum(not item["abstain"] for item in rows),
        "answerable_gold_pages": answerable_gold_pages,
        "parsed_gold_pages": parsed_gold_pages,
        "parsed_gold_quotes": parsed_gold_quotes,
        "top20_retrieved_gold_pages": retrieved_gold_pages,
        "final_cited_gold_pages": cited_gold_pages,
        "exact_quote_citations": exact_quotes,
        "gold_phrases_contained_in_citations": contained_quotes,
        "unanswerable_questions_with_extractive_candidates": unanswerable_with_excerpts,
        "question_results": question_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(
        "evals/pt7-pt8-pt10-pt11-qa-diagnostic-20261023.json"))
    args = parser.parse_args()
    groups = [evaluate_group(group) for group in GROUPS]
    sums = {key: sum(group[key] for group in groups) for key in (
        "questions", "answerable_questions", "answerable_gold_pages", "parsed_gold_pages",
        "parsed_gold_quotes", "top20_retrieved_gold_pages", "final_cited_gold_pages",
        "exact_quote_citations", "gold_phrases_contained_in_citations",
        "unanswerable_questions_with_extractive_candidates")}
    report = {
        "schema_version": 1,
        "dataset_role": "development_diagnostic",
        "groups": groups,
        "totals": sums,
        "configuration": {"candidate_mode": "bm25_expanded", "candidate_limit": 20,
                           "extractive_qa_mode": "bm25", "evidence_limit": 5,
                           "generate": False, "model_calls": 0, "estimated_model_cost_usd": 0},
        "limitations": [
            "仅覆盖 PT7、PT8、PT10、PT11 共 18 题，属于开发诊断，不能外推。",
            "检索页命中与原文摘录覆盖不代表答案语义正确。",
            "不可回答题的非空摘录仅表示关闭生成时返回候选，不代表模型拒答失败。",
        ],
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "totals": sums}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
