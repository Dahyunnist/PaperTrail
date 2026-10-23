"""Measure S1 top-k evidence-page retrieval on the S0 human gold set."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

from .gold import _normalize_excerpt, load_gold
from .s1_index import open_database, search
from .retrieval import retrieve


def evaluate(database: Path, gold_path: Path, k: int = 5,
             minimum_questions: int = 30) -> dict[str, Any]:
    items = load_gold(gold_path, minimum_questions=minimum_questions)
    trace: list[dict[str, Any]] = []
    page_hits = 0
    document_hits = 0
    complete_multi_page = 0
    answerable_count = 0
    for item in items:
        if item["abstain"]:
            continue
        answerable_count += 1
        results = search(database, item["question"], max(k * 5, 20), source_type="original_pdf")
        expected_pages = {(e["sha256"], e["pdf_page"]) for e in item["evidence"]}
        expected_hashes = {e["sha256"] for e in item["evidence"]}
        chunk_top = results[:k]
        pages = _unique_pages(results, k)
        documents = _unique_documents(results, k)
        retrieved_pages = {(r["sha256"], r["pdf_page"]) for r in pages}
        retrieved_hashes = {r["sha256"] for r in chunk_top}
        page_hit = bool(expected_pages.intersection(retrieved_pages))
        chunk_page_hit = bool(expected_pages.intersection(
            {(r["sha256"], r["pdf_page"]) for r in chunk_top if r["pdf_page"] is not None}))
        document_hit = bool(expected_hashes.intersection(retrieved_hashes))
        unique_document_hit = bool(expected_hashes.intersection({r["sha256"] for r in documents}))
        all_pages = bool(expected_pages) and expected_pages.issubset(retrieved_pages)
        page_hits += page_hit
        document_hits += document_hit
        complete_multi_page += all_pages
        trace.append({
            "id": item["id"], "question": item["question"], "question_type": item["question_type"],
            "expected_pages": sorted([{"sha256": h, "pdf_page": p} for h, p in expected_pages], key=lambda x: (x["sha256"], x["pdf_page"])),
            "page_hit_at_k": page_hit, "chunk_page_hit_at_k": chunk_page_hit,
            "document_hit_at_k": document_hit, "unique_document_hit_at_k": unique_document_hit,
            "all_evidence_pages_at_k": all_pages,
            "failure_class": ("hit" if page_hit else "target_document_not_retrieved" if not document_hit
                              else "target_document_retrieved_wrong_page"),
            "chunk_results": [_trace_row(r) for r in chunk_top],
            "page_results": [_trace_row(r) for r in pages],
        })
    unanswerable = []
    for item in load_gold(gold_path, minimum_questions=minimum_questions):
        if not item["abstain"]:
            continue
        results = search(database, item["question"], k, source_type="original_pdf")
        unanswerable.append({"id": item["id"], "question_type": item["question_type"],
                             "retrieval_nonempty": bool(results),
                             "top_score": results[0]["rank_score"] if results else None,
                             "distinct_documents": len({r["sha256"] for r in results})})
    gold_items = load_gold(gold_path, minimum_questions=minimum_questions)
    return {
        "k": k, "answerable_questions": answerable_count,
        "page_recall_at_k": page_hits / answerable_count if answerable_count else 0.0,
        "chunk_page_recall_at_k": sum(r["chunk_page_hit_at_k"] for r in trace) / answerable_count if answerable_count else 0.0,
        "document_recall_at_k": document_hits / answerable_count if answerable_count else 0.0,
        "unique_document_recall_at_k": sum(r["unique_document_hit_at_k"] for r in trace) / answerable_count if answerable_count else 0.0,
        "all_evidence_pages_at_k": complete_multi_page / answerable_count if answerable_count else 0.0,
        "page_hit_count": page_hits, "document_hit_count": document_hits,
        "question_types": {kind: {"total": sum(r["question_type"] == kind for r in trace),
                                   "page_hits": sum(r["question_type"] == kind and r["page_hit_at_k"] for r in trace)}
                           for kind in sorted({r["question_type"] for r in trace})},
        "unanswerable_questions": len(unanswerable), "unanswerable_retrieval": unanswerable,
        "gold_sha256": _file_hash(gold_path), "trace": trace,
    }


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paper_titles(database: Path) -> dict[str, str]:
    conn = open_database(database, readonly=True)
    try:
        return {row["sha256"]: row["title_candidate"] for row in conn.execute(
            "SELECT v.sha256,p.title_candidate FROM paper_versions v JOIN papers p ON p.paper_id=v.paper_id")}
    finally:
        conn.close()


def _trace_row(row: dict[str, Any]) -> dict[str, Any]:
    result = {"sha256": row["sha256"], "paper_id": row["paper_id"],
              "pdf_page": row["pdf_page"], "rank_score": row["rank_score"],
              "source_type": row["source_type"], "chunk_id": row["chunk_id"],
              "text_origin": row.get("text_origin", "native_text")}
    if row.get("retrieval_signals"):
        result["retrieval_signals"] = row["retrieval_signals"]
    if row.get("rerank_usage"):
        result["rerank_usage"] = row["rerank_usage"]
    if row.get("rerank_candidate_pages"):
        result["rerank_candidate_pages"] = row["rerank_candidate_pages"]
    if row.get("rerank_error"):
        result["rerank_error"] = row["rerank_error"]
    return result


def _unique_pages(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    output, seen = [], set()
    for row in results:
        if row["pdf_page"] is None:
            continue
        identity = (row["sha256"], row["pdf_page"])
        if identity in seen:
            continue
        seen.add(identity)
        output.append(row)
        if len(output) >= limit:
            break
    return output


def _unique_documents(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    output, seen = [], set()
    for row in results:
        if row["sha256"] in seen:
            continue
        seen.add(row["sha256"])
        output.append(row)
        if len(output) >= limit:
            break
    return output


def compare_modes(database: Path, gold_path: Path, k: int = 5,
                  modes: tuple[str, ...] = ("bm25", "vector", "hybrid", "bge", "hybrid_bge"),
                  artifact: Path | None = None,
                  minimum_questions: int = 30) -> dict[str, Any]:
    all_items = load_gold(gold_path, minimum_questions=minimum_questions)
    items = [item for item in all_items if not item["abstain"]]
    output: dict[str, Any] = {"k": k, "answerable_questions": len(items), "modes": {}}
    paper_titles = _paper_titles(database)
    for mode in modes:
        page_hits = chunk_page_hits = document_hits = unique_document_hits = complete_hits = candidate_page_hits = 0
        complete_evidence_hits = gold_page_total = gold_page_found_total = evidence_total = evidence_found_total = 0
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        durations: list[float] = []
        by_type: dict[str, dict[str, int]] = {}
        by_paper: dict[str, dict[str, int]] = {}
        trace: list[dict[str, Any]] = []
        for item in items:
            expected_pages = {(e["sha256"], e["pdf_page"]) for e in item["evidence"]}
            expected_hashes = {e["sha256"] for e in item["evidence"]}
            started = time.perf_counter()
            rerank_error = None
            try:
                results = retrieve(database, item["question"], max(k * 5, 20),
                                   source_type="original_pdf", mode=mode, artifact=artifact)
                if mode == "hybrid_bge_rerank":
                    rerank_error = next((row.get("rerank_error") for row in results if row.get("rerank_error")), None)
            except RuntimeError as exc:
                if mode != "hybrid_bge_rerank":
                    raise
                rerank_error = str(exc)
                results = retrieve(database, item["question"], max(k * 5, 20),
                                   source_type="original_pdf", mode="hybrid_bge", artifact=artifact)
            durations.append(time.perf_counter() - started)
            chunk_top = results[:k]
            page_top = _unique_pages(results, k)
            document_top = _unique_documents(results, k)
            ranks = [rank for rank, hit in enumerate(page_top, 1)
                     if (hit["sha256"], hit["pdf_page"]) in expected_pages]
            page_hit = bool(ranks)
            chunk_page_hit = any((hit["sha256"], hit["pdf_page"]) in expected_pages for hit in chunk_top)
            document_hit = any(hit["sha256"] in expected_hashes for hit in chunk_top)
            unique_document_hit = any(hit["sha256"] in expected_hashes for hit in document_top)
            all_pages = expected_pages.issubset({(hit["sha256"], hit["pdf_page"]) for hit in page_top})
            selected_pages = {(hit["sha256"], hit["pdf_page"]) for hit in page_top}
            retrieved_page_text: dict[tuple[str, int], list[str]] = {}
            for hit in results:
                key = (hit["sha256"], hit["pdf_page"])
                if key in selected_pages:
                    retrieved_page_text.setdefault(key, []).append(hit.get("text", ""))
            evidence_matches = []
            for pointer in item["evidence"]:
                key = (pointer["sha256"], pointer["pdf_page"])
                quote = _normalize_excerpt(pointer["quote"])
                evidence_matches.append(any(quote in _normalize_excerpt(text)
                                            for text in retrieved_page_text.get(key, [])))
            complete_evidence = bool(evidence_matches) and all(evidence_matches)
            candidate_pages = {(page["sha256"], page["pdf_page"])
                               for hit in results for page in hit.get("rerank_candidate_pages", [])}
            candidate_hit = bool(expected_pages.intersection(candidate_pages))
            page_hits += page_hit
            chunk_page_hits += chunk_page_hit
            document_hits += document_hit
            unique_document_hits += unique_document_hit
            complete_hits += all_pages
            complete_evidence_hits += complete_evidence
            gold_page_total += len(expected_pages)
            gold_page_found_total += len(expected_pages.intersection(selected_pages))
            evidence_total += len(evidence_matches)
            evidence_found_total += sum(evidence_matches)
            candidate_page_hits += int(candidate_hit)
            reciprocal_ranks.append(1 / ranks[0] if ranks else 0.0)
            dcg = sum(1 / math.log2(rank + 1) for rank in ranks)
            ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(expected_pages), k) + 1))
            ndcgs.append(dcg / ideal if ideal else 0.0)
            group = by_type.setdefault(item["question_type"], {"total": 0, "page_hits": 0})
            group["total"] += 1
            group["page_hits"] += int(page_hit)
            for paper_hash in expected_hashes:
                paper_hit = any(hit["sha256"] == paper_hash for hit in chunk_top)
                paper_page_hit = any(hit["sha256"] == paper_hash and
                                     (hit["sha256"], hit["pdf_page"]) in expected_pages
                                     for hit in page_top)
                paper_evidence = [matches for pointer, matches in zip(item["evidence"], evidence_matches)
                                  if pointer["sha256"] == paper_hash]
                paper_group = by_paper.setdefault(paper_hash, {
                    "title": paper_titles.get(paper_hash, ""),
                    "total": 0, "page_hits": 0, "complete_evidence_hits": 0,
                    "target_document_not_retrieved": 0, "target_document_retrieved_wrong_page": 0,
                    "incomplete_evidence": 0,
                })
                paper_group["total"] += 1
                paper_group["page_hits"] += int(paper_page_hit)
                paper_group["complete_evidence_hits"] += int(bool(paper_evidence) and all(paper_evidence))
                if not paper_hit:
                    paper_group["target_document_not_retrieved"] += 1
                elif not paper_page_hit:
                    paper_group["target_document_retrieved_wrong_page"] += 1
                if paper_page_hit and paper_evidence and not all(paper_evidence):
                    paper_group["incomplete_evidence"] += 1
            trace.append({"id": item["id"], "question": item["question"], "type": item["question_type"],
                          "expected_pages": sorted([list(page) for page in expected_pages]),
                          "page_hit": page_hit, "chunk_page_hit": chunk_page_hit,
                          "document_hit": document_hit, "unique_document_hit": unique_document_hit,
                          "failure_class": ("hit" if page_hit else "target_document_not_retrieved" if not document_hit
                                            else "target_document_retrieved_wrong_page"),
                          "all_evidence_pages": all_pages,
                          "complete_evidence": complete_evidence,
                          "evidence_items_found": sum(evidence_matches),
                          "evidence_items_total": len(evidence_matches),
                          "rerank_candidate_hit": candidate_hit if mode == "hybrid_bge_rerank" else None,
                          "chunk_results": [_trace_row(hit) for hit in chunk_top],
                          "page_results": [_trace_row(hit) for hit in page_top],
                          "rerank_succeeded": rerank_error is None if mode == "hybrid_bge_rerank" else None,
                          "rerank_error": rerank_error})
        total = len(items)
        output["modes"][mode] = {
            "page_recall_at_k": page_hits / total if total else 0,
            "gold_page_recall_at_k": gold_page_found_total / gold_page_total if gold_page_total else 0,
            "chunk_page_recall_at_k": chunk_page_hits / total if total else 0,
            "document_recall_at_k": document_hits / total if total else 0,
            "unique_document_recall_at_k": unique_document_hits / total if total else 0,
            "all_evidence_pages_at_k": complete_hits / total if total else 0,
            "complete_evidence_at_k": complete_evidence_hits / total if total else 0,
            "evidence_item_recall_at_k": evidence_found_total / evidence_total if evidence_total else 0,
            "rerank_candidate_page_recall": candidate_page_hits / total if mode == "hybrid_bge_rerank" and total else None,
            "mrr_at_k": sum(reciprocal_ranks) / total if total else 0,
            "ndcg_at_k": sum(ndcgs) / total if total else 0,
            "mean_query_ms": sum(durations) * 1000 / total if total else 0,
            "page_hits": page_hits, "document_hits": document_hits,
            "by_question_type": by_type, "by_paper": by_paper, "trace": trace,
        }
        unanswerable_items = [item for item in all_items if item["abstain"]]
        unanswerable = []
        for item in unanswerable_items:
            results = retrieve(database, item["question"], k, source_type="original_pdf", mode=mode, artifact=artifact)
            unanswerable.append({"id": item["id"], "retrieval_nonempty": bool(results),
                                 "top_score": results[0]["rank_score"] if results else None})
        output["modes"][mode]["unanswerable_retrieval"] = unanswerable
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    parser.add_argument("--gold", type=Path, default=Path("evals/gold.jsonl"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--minimum-questions", type=int, default=30)
    parser.add_argument("--trace-out", type=Path, default=Path(".local/s1-retrieval-trace.json"))
    parser.add_argument("--compare", action="store_true", help="对照 BM25、潜在向量和 RRF 混合检索")
    parser.add_argument("--vector-artifact", type=Path)
    parser.add_argument("--modes", nargs="+", choices=["bm25", "vector", "hybrid", "bge", "hybrid_bge", "hybrid_bge_wide", "hybrid_bge_dense_rerank", "hybrid_bge_rerank"])
    args = parser.parse_args()
    result = compare_modes(args.db, args.gold, args.k,
                           modes=tuple(args.modes) if args.modes else ("bm25", "vector", "hybrid", "bge", "hybrid_bge"),
                           artifact=args.vector_artifact,
                           minimum_questions=args.minimum_questions) if args.compare else evaluate(
                               args.db, args.gold, args.k, minimum_questions=args.minimum_questions)
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
