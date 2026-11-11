"""Post-hoc PT2 repair evaluation on private, disposable copies of frozen inputs."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.page_ranking import resolve_explicit_paper_pair, retrieve_explicit_two_paper_pages
from papertrail.retrieval import bm25_search, hybrid_search, retrieve, vector_search
from papertrail.s1_index import open_database

GOLD = ROOT / "evals/pt9-pt12-final-heldout-gold-20261023.jsonl"
DATABASE = ROOT / ".local/pt-public-all-20261023.sqlite3"
VECTOR = ROOT / ".local/pt-public-all-20261023.vectors.joblib"
BASELINE = ROOT / ".local/pt9-pt12-final-retrieval-k10.json"
PRIOR_DIAGNOSTIC = ROOT / "evals/pt2-parent-page-diagnostic-20261111.json"
OUTPUT = ROOT / "evals/pt2-two-paper-balance-20261111.json"
WORK = ROOT / ".tmp/pt2-two-paper-eval-20261111"
TARGET_IDS = {"PT9-03", "PT12-05"}
EXPECTED = {
    "gold": "e03aaec49d953664841ab9cf3e17f079829597dc2200e8c071e1d80f9c1b510c",
    "baseline": "cb84f619054a9709d2cb79e2fdb6127ba032a2d7b50ed275d5d287c6837ef6fd",
    "database": "ef5f72491e4b7be9872d56a9621ffa57a1f8335506ba2394c039e7d999837a24",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_rank(rows: list[dict[str, Any]], sha: str, page: int) -> int | None:
    return next((rank for rank, row in enumerate(rows, 1)
                 if row["sha256"] == sha and row["pdf_page"] == page), None)


def unique_pages(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for row in rows:
        key = (row["sha256"], row["pdf_page"])
        if key not in seen:
            seen.add(key)
            output.append(row)
            if len(output) >= limit:
                break
    return output


def mrr(rows: list[dict[str, Any]], expected: set[tuple[str, int]], k: int) -> float:
    rank = next((index for index, row in enumerate(rows[:k], 1)
                 if (row["sha256"], row["pdf_page"]) in expected), None)
    return 1 / rank if rank else 0.0


def main() -> None:
    input_hashes = {"gold": sha256(GOLD), "baseline": sha256(BASELINE),
                    "database": sha256(DATABASE), "vector_index": sha256(VECTOR)}
    for name in ("gold", "baseline", "database"):
        if input_hashes[name] != EXPECTED[name]:
            raise SystemExit(f"冻结输入哈希变化：{name}")
    WORK.mkdir(parents=True, exist_ok=True)
    eval_db, eval_vector = WORK / "eval.sqlite3", WORK / "eval.vectors.joblib"
    shutil.copy2(DATABASE, eval_db)
    shutil.copy2(VECTOR, eval_vector)
    copied_db_before_migration = sha256(eval_db)
    schema_conn = open_database(eval_db)
    schema_conn.close()

    gold_by_id = {json.loads(line)["id"]: json.loads(line)
                  for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()}
    old = json.loads(BASELINE.read_text(encoding="utf-8"))
    old_trace = {row["id"]: row for row in old["modes"]["hybrid"]["trace"]}
    prior = json.loads(PRIOR_DIAGNOSTIC.read_text(encoding="utf-8"))
    previous_parent = {row["question_id"]: row for row in prior["results"]}
    results = []
    for question_id in sorted(TARGET_IDS):
        item = gold_by_id[question_id]
        query = item["question"]

        # Retrieval receives only query text. Expected evidence is read after all rankings exist.
        resolved = resolve_explicit_paper_pair(eval_db, query)
        if not resolved:
            raise SystemExit(f"无法从 query 与来源标题解析双论文：{question_id}")
        aliases, clean_query = resolved
        base_bm25 = bm25_search(eval_db, query, 200, source_type="original_pdf", readonly=True)
        base_vector = vector_search(eval_db, query, 200, source_type="original_pdf", artifact=eval_vector)
        base_hybrid50 = hybrid_search(eval_db, query, 50, source_type="original_pdf", artifact=eval_vector)
        base_hybrid100 = hybrid_search(eval_db, query, 100, source_type="original_pdf", artifact=eval_vector)
        default_rows = retrieve(eval_db, query, 50, source_type="original_pdf",
                                mode="hybrid", artifact=eval_vector)
        default_chunk_keys = [(row["sha256"], row["pdf_page"], row["chunk_id"])
                              for row in default_rows[:10]]
        frozen_chunk_keys = [(row["sha256"], row["pdf_page"], row["chunk_id"])
                             for row in old_trace[question_id]["chunk_results"]]
        default_page_keys = [(row["sha256"], row["pdf_page"])
                             for row in unique_pages(default_rows, 10)]
        frozen_page_keys = [(row["sha256"], row["pdf_page"])
                            for row in old_trace[question_id]["page_results"]]
        if default_chunk_keys != frozen_chunk_keys or default_page_keys != frozen_page_keys:
            raise SystemExit(f"默认hybrid前10结果相对冻结轨迹发生变化：{question_id}")
        base_pages10 = old_trace[question_id]["page_results"]
        base_pages20 = unique_pages(base_hybrid100, 20)

        new_bm25 = bm25_search(eval_db, clean_query, 200, source_type="original_pdf", readonly=True)
        new_vector = vector_search(eval_db, clean_query, 200, source_type="original_pdf", artifact=eval_vector)
        repaired = retrieve_explicit_two_paper_pages(
            eval_db, query, limit_per_paper=10, artifact=eval_vector, candidate_depth=200)

        # Gold pointers are used only now, to score already materialized retrieval results.
        expected = {(evidence["sha256"], evidence["pdf_page"]) for evidence in item["evidence"]}
        if not expected:
            raise SystemExit(f"目标题缺少冻结证据：{question_id}")
        pages = []
        for evidence in item["evidence"]:
            sha, page = evidence["sha256"], evidence["pdf_page"]
            key = (sha, page)
            baseline_hybrid_rank = first_rank(base_hybrid50, sha, page)
            baseline_page_rank20 = first_rank(base_pages20, sha, page)
            new_page = next((row for row in repaired
                             if row["sha256"] == sha and row["pdf_page"] == page), None)
            raw_bm_rank = first_rank(new_bm25, sha, page)
            raw_vector_rank = first_rank(new_vector, sha, page)
            output_rank = first_rank(repaired, sha, page)
            pages.append({
                "source_sha256": sha,
                "pdf_page": page,
                "baseline": {
                    "bm25_candidate_rank_200": first_rank(base_bm25, sha, page),
                    "vector_candidate_rank_200": first_rank(base_vector, sha, page),
                    "rrf_chunk_rank_50": baseline_hybrid_rank,
                    "unique_page_rank_10": first_rank(base_pages10, sha, page),
                    "unique_page_rank_20": baseline_page_rank20,
                    "filter_reason": (
                        "全局RRF候选未进Top-50，之后无页可选" if baseline_hybrid_rank is None else
                        "进入Top-50，但重复页占位后唯一页名次超过10" if
                        first_rank(base_pages10, sha, page) is None else
                        "保留在旧基线Top-10唯一页中")
                },
                "repaired": {
                    "bm25_candidate_rank_200_after_query_cleanup": raw_bm_rank,
                    "vector_candidate_rank_200_after_query_cleanup": raw_vector_rank,
                    "candidate_union_hit_200": raw_bm_rank is not None or raw_vector_rank is not None,
                    "paper_scoped_fused_page_rank": new_page["source_local_page_rank"] if new_page else None,
                    "round_robin_output_rank": output_rank,
                    "included_at_k10": output_rank is not None and output_rank <= 10,
                    "included_at_k20": output_rank is not None and output_rank <= 20,
                    "filter_reason": (
                        "保留在指定论文页额内" if new_page and output_rank is not None and output_rank <= 10 else
                        "进入论文页额，但轮询后的全局K=10截断" if new_page else
                        "未进入BM25/向量Top-200候选并被页额筛掉")
                }
            })
        baseline_pages10_found = sum(page["baseline"]["unique_page_rank_10"] is not None for page in pages)
        baseline_pages20_found = sum(page["baseline"]["unique_page_rank_20"] is not None for page in pages)
        repaired_pages10_found = sum(page["repaired"]["included_at_k10"] for page in pages)
        repaired_pages20_found = sum(page["repaired"]["included_at_k20"] for page in pages)
        modality_union_found = sum(page["repaired"]["candidate_union_hit_200"] for page in pages)
        hybrid50_found = sum(page["baseline"]["rrf_chunk_rank_50"] is not None for page in pages)
        results.append({
            "question_id": question_id,
            "paper_aliases": [alias for alias, _ in aliases],
            "gold_page_count": len(expected),
            "baseline": {"gold_pages_found_at_10": baseline_pages10_found,
                         "gold_pages_found_at_20": baseline_pages20_found,
                         "hybrid_candidate_coverage_at_50": hybrid50_found,
                         "mrr_at_10": mrr(base_pages10, expected, 10),
                         "mrr_at_20": mrr(base_pages20, expected, 20),
                         "default_top10_matches_frozen_chunk_and_page_trace": True},
            "repaired": {"gold_pages_found_at_10": repaired_pages10_found,
                         "gold_pages_found_at_20": repaired_pages20_found,
                         "modality_candidate_coverage_at_200": modality_union_found,
                         "mrr_at_10": mrr(repaired, expected, 10),
                         "mrr_at_20": mrr(repaired, expected, 20),
                         "paper_scoped_pages_returned": len(repaired)},
            "pages": pages,
            "prior_parent_page_strategy_gold_pages_found_at_10": previous_parent[question_id]["gold_pages_found"]
        })

    totals = {"gold_pages": sum(row["gold_page_count"] for row in results),
              "questions": len(results)}
    for k in (10, 20):
        base_found = sum(row["baseline"][f"gold_pages_found_at_{k}"] for row in results)
        new_found = sum(row["repaired"][f"gold_pages_found_at_{k}"] for row in results)
        totals[f"baseline_page_recall_at_{k}"] = base_found / totals["gold_pages"]
        totals[f"repaired_page_recall_at_{k}"] = new_found / totals["gold_pages"]
        totals[f"baseline_complete_questions_at_{k}"] = sum(
            row["baseline"][f"gold_pages_found_at_{k}"] == row["gold_page_count"] for row in results)
        totals[f"repaired_complete_questions_at_{k}"] = sum(
            row["repaired"][f"gold_pages_found_at_{k}"] == row["gold_page_count"] for row in results)
    totals["baseline_hybrid_candidate_coverage_at_50"] = sum(
        row["baseline"]["hybrid_candidate_coverage_at_50"] for row in results) / totals["gold_pages"]
    totals["baseline_modality_candidate_coverage_at_200"] = sum(
        any(page["baseline"][f"{mode}_candidate_rank_200"] is not None for mode in ("bm25", "vector"))
        for row in results for page in row["pages"]) / totals["gold_pages"]
    totals["repaired_modality_candidate_coverage_at_200"] = sum(
        row["repaired"]["modality_candidate_coverage_at_200"] for row in results) / totals["gold_pages"]
    for k in (10, 20):
        totals[f"baseline_mrr_at_{k}"] = sum(row["baseline"][f"mrr_at_{k}"] for row in results) / len(results)
        totals[f"repaired_mrr_at_{k}"] = sum(row["repaired"][f"mrr_at_{k}"] for row in results) / len(results)
    totals["default_retrieval_matches_frozen_top10"] = all(
        row["baseline"]["default_top10_matches_frozen_chunk_and_page_trace"] for row in results)
    source_unchanged = {"gold": sha256(GOLD) == input_hashes["gold"],
                        "baseline": sha256(BASELINE) == input_hashes["baseline"],
                        "database": sha256(DATABASE) == input_hashes["database"],
                        "vector_index": sha256(VECTOR) == input_hashes["vector_index"]}
    if not all(source_unchanged.values()):
        raise SystemExit("原始冻结输入在评测期间发生变化")
    report = {
        "schema_version": 1,
        "status": "development_diagnostic_independent_copy_nonblind",
        "purpose": "诊断并比较PT2两个遗留跨论文漏检；不改历史评测分数或冻结输入。",
        "method": {
            "name": "explicit-two-paper scoped parent-page fusion",
            "retrieval_input": "question text and indexed paper titles only; gold evidence pointers are read after candidate lists are frozen",
            "query_cleanup": "remove the two hyphenated paper aliases from the query to reduce title-page bias",
            "candidate_depth_per_modality": 200,
            "page_score": "within-paper child RRF (BM25=2.0, vector=0.5, k=60), then sum best scores from two distinct parents",
            "selection": "up to 10 pages per explicitly named paper, round-robin interleave; fallback/default retrieval unchanged",
            "independent_copy": "index schema migrated only in a disposable copy under ignored .tmp"
        },
        "frozen_inputs": {**input_hashes, "independent_copy_before_schema_migration_sha256": copied_db_before_migration,
                          "independent_copy_after_schema_migration_sha256": sha256(eval_db),
                          "source_unchanged_after_evaluation": source_unchanged},
        "scope": totals,
        "results": results,
        "limitations": [
            "开发集/非盲固定回归；不是盲测、泛化评测或新基线。",
            "只对问题明确含两篇连字符论文别名且能唯一映射到标题的查询启用；其他问题走原路径。",
            "PT9-03仍需K=20才能同时保留两页；K=10页Recall未满，不能声称两题均完全修复。",
            "未调用模型；输出无题干、gold引文、PDF正文或本机路径。"
        ]
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "scope": totals,
                      "all_sources_unchanged": all(source_unchanged.values())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
