"""Measure S1 top-k evidence-page retrieval on the S0 human gold set."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

from .gold import load_gold
from .s1_index import search
from .retrieval import retrieve


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


def compare_modes(database: Path, gold_path: Path, k: int = 5,
                  modes: tuple[str, ...] = ("bm25", "vector", "hybrid"),
                  artifact: Path | None = None) -> dict[str, Any]:
    items = [item for item in load_gold(gold_path) if not item["abstain"]]
    output: dict[str, Any] = {"k": k, "answerable_questions": len(items), "modes": {}}
    for mode in modes:
        page_hits = document_hits = complete_hits = 0
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        durations: list[float] = []
        by_type: dict[str, dict[str, int]] = {}
        trace: list[dict[str, Any]] = []
        for item in items:
            expected_pages = {(e["sha256"], e["pdf_page"]) for e in item["evidence"]}
            expected_hashes = {e["sha256"] for e in item["evidence"]}
            started = time.perf_counter()
            results = retrieve(database, item["question"], k, mode=mode, artifact=artifact)
            durations.append(time.perf_counter() - started)
            ranks = [rank for rank, hit in enumerate(results, 1)
                     if (hit["sha256"], hit["pdf_page"]) in expected_pages]
            page_hit = bool(ranks)
            document_hit = any(hit["sha256"] in expected_hashes for hit in results)
            all_pages = expected_pages.issubset({(hit["sha256"], hit["pdf_page"]) for hit in results})
            page_hits += page_hit
            document_hits += document_hit
            complete_hits += all_pages
            reciprocal_ranks.append(1 / ranks[0] if ranks else 0.0)
            dcg = sum(1 / math.log2(rank + 1) for rank in ranks)
            ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(expected_pages), k) + 1))
            ndcgs.append(dcg / ideal if ideal else 0.0)
            group = by_type.setdefault(item["question_type"], {"total": 0, "page_hits": 0})
            group["total"] += 1
            group["page_hits"] += int(page_hit)
            trace.append({"id": item["id"], "type": item["question_type"],
                          "expected_pages": sorted([list(page) for page in expected_pages]),
                          "page_hit": page_hit, "document_hit": document_hit,
                          "all_evidence_pages": all_pages,
                          "results": [{"sha256": hit["sha256"], "pdf_page": hit["pdf_page"],
                                       "score": hit["rank_score"], "chunk_id": hit["chunk_id"]}
                                      for hit in results]})
        total = len(items)
        output["modes"][mode] = {
            "page_recall_at_k": page_hits / total if total else 0,
            "document_recall_at_k": document_hits / total if total else 0,
            "all_evidence_pages_at_k": complete_hits / total if total else 0,
            "mrr_at_k": sum(reciprocal_ranks) / total if total else 0,
            "ndcg_at_k": sum(ndcgs) / total if total else 0,
            "mean_query_ms": sum(durations) * 1000 / total if total else 0,
            "page_hits": page_hits, "document_hits": document_hits,
            "by_question_type": by_type, "trace": trace,
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    parser.add_argument("--gold", type=Path, default=Path("evals/gold.jsonl"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--trace-out", type=Path, default=Path(".local/s1-retrieval-trace.json"))
    parser.add_argument("--compare", action="store_true", help="对照 BM25、潜在向量和 RRF 混合检索")
    parser.add_argument("--vector-artifact", type=Path)
    args = parser.parse_args()
    result = compare_modes(args.db, args.gold, args.k, artifact=args.vector_artifact) if args.compare else evaluate(args.db, args.gold, args.k)
    args.trace_out.parent.mkdir(parents=True, exist_ok=True)
    args.trace_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.compare:
        for mode, metrics in result["modes"].items():
            print(f"{mode}: page_recall@{args.k}={metrics['page_recall_at_k']:.3f} "
                  f"MRR={metrics['mrr_at_k']:.3f} nDCG={metrics['ndcg_at_k']:.3f} "
                  f"mean_query_ms={metrics['mean_query_ms']:.1f}")
    else:
        print(f"k={result['k']} answerable={result['answerable_questions']} page_recall={result['page_recall_at_k']:.3f} ({result['page_hit_count']}/{result['answerable_questions']}) document_recall={result['document_recall_at_k']:.3f} ({result['document_hit_count']}/{result['answerable_questions']}) trace={args.trace_out}")
    print(f"trace={args.trace_out}")


if __name__ == "__main__":
    main()
