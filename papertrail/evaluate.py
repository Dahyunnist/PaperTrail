"""Measure S1 top-k evidence-page retrieval on the S0 human gold set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .gold import load_gold
from .s1_index import search


def evaluate(database: Path, gold_path: Path, k: int = 5) -> dict[str, Any]:
    items = load_gold(gold_path)
    trace: list[dict[str, Any]] = []
    page_hits = 0
    document_hits = 0
    complete_multi_page = 0
    answerable_count = 0
    for item in items:
        if item["abstain"]:
            continue
        answerable_count += 1
        results = search(database, item["question"], k)
        expected_pages = {(e["sha256"], e["pdf_page"]) for e in item["evidence"]}
        expected_hashes = {e["sha256"] for e in item["evidence"]}
        retrieved_pages = {(r["sha256"], r["pdf_page"]) for r in results if r["pdf_page"] is not None}
        retrieved_hashes = {r["sha256"] for r in results}
        page_hit = bool(expected_pages.intersection(retrieved_pages))
        document_hit = bool(expected_hashes.intersection(retrieved_hashes))
        all_pages = bool(expected_pages) and expected_pages.issubset(retrieved_pages)
        page_hits += page_hit
        document_hits += document_hit
        complete_multi_page += all_pages
        trace.append({
            "id": item["id"], "question_type": item["question_type"],
            "expected_pages": sorted([{"sha256": h, "pdf_page": p} for h, p in expected_pages], key=lambda x: (x["sha256"], x["pdf_page"])),
            "page_hit_at_k": page_hit, "document_hit_at_k": document_hit, "all_evidence_pages_at_k": all_pages,
            "results": [{"sha256": r["sha256"], "pdf_page": r["pdf_page"], "rank_score": r["rank_score"], "source_type": r["source_type"], "chunk_id": r["chunk_id"]} for r in results],
        })
    return {
        "k": k, "answerable_questions": answerable_count,
        "page_recall_at_k": page_hits / answerable_count if answerable_count else 0.0,
        "document_recall_at_k": document_hits / answerable_count if answerable_count else 0.0,
        "all_evidence_pages_at_k": complete_multi_page / answerable_count if answerable_count else 0.0,
        "page_hit_count": page_hits, "document_hit_count": document_hits,
        "trace": trace,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    parser.add_argument("--gold", type=Path, default=Path("evals/gold.jsonl"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--trace-out", type=Path, default=Path(".local/s1-retrieval-trace.json"))
    args = parser.parse_args()
    result = evaluate(args.db, args.gold, args.k)
    args.trace_out.parent.mkdir(parents=True, exist_ok=True)
    args.trace_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"k={result['k']} answerable={result['answerable_questions']} page_recall={result['page_recall_at_k']:.3f} ({result['page_hit_count']}/{result['answerable_questions']}) document_recall={result['document_recall_at_k']:.3f} ({result['document_hit_count']}/{result['answerable_questions']}) trace={args.trace_out}")


if __name__ == "__main__":
    main()
