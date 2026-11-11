"""Post-hoc offline diagnosis of the three missed PT9/PT12 evidence queries."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.page_ranking import retrieve_parent_pages
from papertrail.retrieval import bm25_search, hybrid_search, vector_search

GOLD = ROOT / "evals/pt9-pt12-final-heldout-gold-20261023.jsonl"
DATABASE = ROOT / ".local/pt-public-all-20261023.sqlite3"
VECTOR = ROOT / ".local/pt-public-all-20261023.vectors.joblib"
PREREG = ROOT / "evals/pt15-model-e2e-prereg-20261023.json"
BASELINE = ROOT / ".local/pt9-pt12-final-retrieval-k10.json"
OUTPUT = ROOT / "evals/pt2-parent-page-diagnostic-20261111.json"
TARGET_IDS = {"PT9-03", "PT9-05", "PT12-05"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rank_for_page(rows: list[dict[str, Any]], sha: str, page: int) -> int | None:
    return next((index for index, row in enumerate(rows, 1)
                 if row["sha256"] == sha and row["pdf_page"] == page), None)


def main() -> None:
    gold = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    old = json.loads(BASELINE.read_text(encoding="utf-8"))
    old_trace = {row["id"]: row for row in old["modes"]["hybrid"]["trace"]}
    failed_ids = {qid for qid, row in old_trace.items() if not row["complete_evidence"]}
    if failed_ids != TARGET_IDS:
        raise SystemExit(f"原始k=10失败题与审计清单不符：{sorted(failed_ids)}")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    locked_hashes = dict(prereg["locked_hashes"]["source_code"])
    locked_hashes["papertrail/local_llm.py"] = prereg["locked_hashes"].get("local_llm_sha256")
    frozen_hash_check = {}
    for relative, registered in locked_hashes.items():
        if not registered:
            continue
        head_bytes = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT,
                                    check=True, capture_output=True).stdout
        working = sha256(ROOT / relative)
        head_sha = hashlib.sha256(head_bytes).hexdigest()
        diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", relative], cwd=ROOT)
        unchanged = diff.returncode == 0
        frozen_hash_check[relative] = {"registered_sha256": registered, "head_blob_sha256": head_sha,
                                       "working_file_sha256": working, "unchanged_in_git": unchanged}
        if not unchanged:
            raise SystemExit(f"本轮改动了冻结评测源文件：{relative}")
    prereg_relative = str(PREREG.relative_to(ROOT)).replace("\\", "/")
    prereg_head = subprocess.run(["git", "show", f"HEAD:{prereg_relative}"], cwd=ROOT,
                                 check=True, capture_output=True).stdout
    prereg_diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", prereg_relative], cwd=ROOT)
    if prereg_diff.returncode != 0:
        raise SystemExit("本轮改动了PT15预登记文件")
    if sha256(GOLD) != "e03aaec49d953664841ab9cf3e17f079829597dc2200e8c071e1d80f9c1b510c":
        raise SystemExit("PT9/PT12冻结gold哈希变化")
    selected = [item for item in gold if item["id"] in TARGET_IDS and not item["abstain"]]
    if {item["id"] for item in selected} != TARGET_IDS:
        raise SystemExit("冻结集缺少目标问题")
    rows = []
    for item in selected:
        baseline = old_trace[item["id"]]
        pages = retrieve_parent_pages(DATABASE, item["question"], limit=10, artifact=VECTOR,
                                      candidate_multiplier=20)
        bm25 = bm25_search(DATABASE, item["question"], limit=800)
        vector = vector_search(DATABASE, item["question"], limit=800, artifact=VECTOR)
        baseline_bm25 = bm25_search(DATABASE, item["question"], limit=200)
        baseline_vector = vector_search(DATABASE, item["question"], limit=200, artifact=VECTOR)
        baseline_candidates = hybrid_search(DATABASE, item["question"], limit=50, artifact=VECTOR)
        baseline_pages = baseline["page_results"]
        page_ranks = []
        for evidence in item["evidence"]:
            target_sha, target_page = evidence["sha256"], evidence["pdf_page"]
            page_ranks.append({
                "sha256": target_sha,
                "pdf_page": target_page,
                "baseline_chunk_top10_hit": rank_for_page(baseline["chunk_results"], target_sha, target_page) is not None,
                "baseline_page_top10_rank": rank_for_page(baseline_pages, target_sha, target_page),
                "bm25_candidate_rank_at_200": rank_for_page(baseline_bm25, target_sha, target_page),
                "vector_candidate_rank_at_200": rank_for_page(baseline_vector, target_sha, target_page),
                "hybrid_candidate_rank_at_50": rank_for_page(baseline_candidates, target_sha, target_page),
                "parent_page_rank_at_10": rank_for_page(pages, target_sha, target_page),
            })
        got = sum(rank["parent_page_rank_at_10"] is not None for rank in page_ranks)
        rows.append({"question_id": item["id"], "gold_pages": len(page_ranks),
                     "baseline_complete_evidence": baseline["complete_evidence"],
                     "parent_page_complete_evidence_at_10": got == len(page_ranks),
                     "gold_pages_found": got, "page_ranks": page_ranks})
    gold_pages = sum(row["gold_pages"] for row in rows)
    found = sum(row["gold_pages_found"] for row in rows)
    report = {
        "schema_version": 1,
        "status": "posthoc_seen_set_diagnostic_not_blind",
        "purpose": "PT2诊断原始k=10混合检索漏掉的三个问题；不改历史评测结果或冻结输入",
        "common_cause": "全语料按子块做RRF并全局截断；未按来源页聚合或为多论文问题分配来源预算，目标页在单路候选中出现但被全局融合/截断挤出。",
        "minimal_repair": "独立可选检索器先扩展候选，再按不同父段聚合为唯一来源页；保留每个被选页的全部候选子块ID。",
        "frozen_inputs_unchanged": {"gold_sha256_matches_expected": True,
                                    "prereg_file_sha256": sha256(PREREG),
                                    "prereg_file_matches_head": True,
                                    "source_files_unchanged_since_head": frozen_hash_check},
        "baseline_report": str(BASELINE.relative_to(ROOT)),
        "baseline_report_sha256": sha256(BASELINE),
        "gold_file": str(GOLD.relative_to(ROOT)),
        "gold_sha256": sha256(GOLD),
        "database_sha256": sha256(DATABASE),
        "method": {"name": "distinct-parent page aggregation", "candidate_multiplier": 20,
                   "baseline_return_limit_before_page_dedup": 50,
                   "baseline_candidate_pool_per_modality": 200, "baseline_rrf_weights": {"bm25": 2.0, "vector": 0.5},
                   "final_page_limit": 10,
                   "score": "每页取分数最高的两个不同父段RRF分数之和；父段内保留全部候选子块引用"},
        "scope": {"questions": len(rows), "gold_pages": gold_pages,
                  "baseline_complete_evidence_rate": old["modes"]["hybrid"]["complete_evidence_at_k"],
                  "baseline_complete_evidence_questions": round(old["modes"]["hybrid"]["complete_evidence_at_k"] * old["answerable_questions"]),
                  "parent_page_gold_pages_found": found,
                  "parent_page_complete_questions": sum(row["parent_page_complete_evidence_at_10"] for row in rows)},
        "results": rows,
        "limitations": ["题目和来源已暴露；本报告是诊断，不是独立评测或新基线。",
                        "历史k=10结果仍为7/10；页聚合仅修复PT9-05，PT9-03与PT12-05仍漏页。",
                        "候选策略不接入默认路径；未调用模型，未写入索引、gold或原报告。"],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "scope": report["scope"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
