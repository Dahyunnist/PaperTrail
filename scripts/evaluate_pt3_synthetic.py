"""Run the frozen PT3 synthetic-only QA set under the reconciled model budget."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.gold import load_gold, verify_quotes
from papertrail.qa import ask
from papertrail.s1_index import index_selection


HISTORICAL_LEDGERS = (
    ".local/p6-api-usage.json",
    ".local/p12-synthetic-usage.json",
    ".local/p13-api-usage.json",
    ".local/p13-repeat-api-usage-20261023.json",
)
MASTER_LEDGER = ROOT / ".local/pt-master-usage.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _request_key(row: dict) -> tuple:
    return (row.get("at"), row.get("model"), row.get("prompt_chars"),
            row.get("prompt_tokens"), row.get("completion_tokens"))


def _master_usage() -> dict:
    historical = {}
    for name in HISTORICAL_LEDGERS:
        ledger_path = ROOT / name
        if not ledger_path.is_file():
            raise SystemExit(f"历史模型账本缺失：{name}")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        for row in ledger.get("requests", []):
            historical.setdefault(_request_key(row), row)
    minimum_spend = round(sum(float(row.get("cost_upper_bound_usd", 0))
                              for row in historical.values()), 8)

    if MASTER_LEDGER.exists():
        master = json.loads(MASTER_LEDGER.read_text(encoding="utf-8"))
        known = {_request_key(row) for row in master.get("requests", [])}
        if not set(historical).issubset(known):
            raise SystemExit("主账本缺少历史请求；拒绝用旧账本覆盖新支出")
        if float(master.get("spent_upper_bound_usd", 0)) < minimum_spend:
            raise SystemExit("主账本累计支出低于历史去重总额")
    else:
        master = {"cap_usd": 0.50, "spent_upper_bound_usd": minimum_spend,
                  "requests": list(historical.values()),
                  "reconciliation": {"historical_entries": sum(
                      len(json.loads((ROOT / name).read_text(encoding="utf-8")).get("requests", []))
                      for name in HISTORICAL_LEDGERS),
                      "unique_historical_requests": len(historical),
                      "deduplication_key": ["at", "model", "prompt_chars", "prompt_tokens", "completion_tokens"]}}
        MASTER_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        MASTER_LEDGER.write_text(json.dumps(master, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if float(master.get("spent_upper_bound_usd", 0)) > 0.50:
        raise SystemExit("已达到 $0.50 硬上限；禁止继续调用")
    return master


def _snapshot() -> tuple[int, float, int, int]:
    ledger = json.loads(MASTER_LEDGER.read_text(encoding="utf-8"))
    rows = ledger.get("requests", [])
    return (len(rows), float(ledger.get("spent_upper_bound_usd", 0)),
            sum(int(row.get("prompt_tokens") or 0) for row in rows),
            sum(int(row.get("completion_tokens") or 0) for row in rows))


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=ROOT / "evals/pt3-synthetic-gold-20261023.jsonl")
    parser.add_argument("--manifest", type=Path, default=ROOT / "evals/pt3-synthetic-manifest-20261023.json")
    parser.add_argument("--sources", type=Path, default=ROOT / "evals/fixtures/pt3-synthetic/sources.yaml")
    parser.add_argument("--database", type=Path, default=ROOT / ".local/pt3-synthetic-model.sqlite3")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/pt3-synthetic-model-20261023.json")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if _sha256(args.gold) != manifest["gold_sha256"]:
        raise SystemExit("PT3 黄金集哈希与冻结清单不匹配")
    for file_name, expected in manifest["sources"].items():
        if _sha256(ROOT / "evals/fixtures/pt3-synthetic" / file_name) != expected:
            raise SystemExit(f"合成 PDF 哈希与冻结清单不匹配：{file_name}")
    items = load_gold(args.gold, minimum_questions=1)
    verify_quotes(items, args.sources)
    if not os.environ.get("PAPERTRAIL_LLM_MODEL"):
        raise SystemExit("请先设置 PAPERTRAIL_LLM_MODEL；本脚本只允许冻结的合成资料")
    if args.database.exists() or args.out.exists():
        raise SystemExit("评测数据库或报告已存在；拒绝重复调用或覆盖旧结果")

    _master_usage()
    os.environ["PAPERTRAIL_LLM_BUDGET_FILE"] = str(MASTER_LEDGER)
    os.environ["PAPERTRAIL_LLM_BUDGET_USD"] = "0.50"
    selection_path = ROOT / ".local/pt3-synthetic-selection.jsonl"
    selection = []
    for file_name, digest in manifest["sources"].items():
        selection.append({"root_id": "pt3_synthetic", "file_name": file_name,
                          "relative_path": file_name, "sha256": digest,
                          "kind": "pdf", "source_type": "original_pdf"})
    selection_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selection),
                              encoding="utf-8")
    indexed = index_selection(args.database, args.sources, selection_path)
    if indexed["added"] != len(selection) or indexed["issues"]:
        raise SystemExit(f"合成资料索引未完整成功：{indexed}")

    initial = _snapshot()
    report = {"dataset_id": manifest["dataset_id"], "gold_sha256": manifest["gold_sha256"],
              "source_sha256": manifest["sources"], "synthetic_only": True,
              "model": os.environ["PAPERTRAIL_LLM_MODEL"], "provider": os.environ.get("PAPERTRAIL_LLM_PROVIDER"),
              "budget_start_usd": initial[1], "budget_ceiling_usd": 0.50,
              "cases": []}
    for item in items:
        before = _snapshot()
        started = time.perf_counter()
        case = {"id": item["id"], "question": item["question"],
                "expected_answer": item["expected_answer"], "abstain_expected": item["abstain"],
                "human_review": None}
        try:
            result = ask(args.database, item["question"], conversation_id=f"pt3-{item['id']}",
                         limit=8, mode="bm25", generate=True)
            evidence = [claim.get("evidence") for claim in result["claims"] if claim.get("evidence")]
            case.update({"status": result["status"], "answer": result["answer"],
                         "coverage_complete": result["coverage_complete"],
                         "coverage_gaps": result["coverage_gaps"],
                         "coverage_requirements": result["coverage_requirements"],
                         "missing_subquestions": result["missing_subquestions"],
                         "claims": result["claims"], "citations": evidence,
                         "diagnostics": (result.get("usage") or {}).get("_diagnostics", {})})
        except Exception as exc:
            case["error"] = f"{type(exc).__name__}: {exc}"
        after = _snapshot()
        case["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        case["api_requests"] = after[0] - before[0]
        case["prompt_tokens"] = after[2] - before[2]
        case["completion_tokens"] = after[3] - before[3]
        case["cost_upper_bound_usd"] = round(after[1] - before[1], 8)
        report["cases"].append(case)
        report["budget_end_usd"] = after[1]
        _write_report(args.out, report)
        if "budget cap reached" in case.get("error", ""):
            break
    end = _snapshot()
    report["summary"] = {"completed_questions": len(report["cases"]),
                         "api_requests": end[0] - initial[0],
                         "prompt_tokens": end[2] - initial[2],
                         "completion_tokens": end[3] - initial[3],
                         "cost_upper_bound_usd": round(end[1] - initial[1], 8),
                         "budget_end_usd": end[1],
                         "median_latency_ms": round(statistics.median(
                             case["latency_ms"] for case in report["cases"]), 2)
                             if report["cases"] else None}
    _write_report(args.out, report)
    print(json.dumps({"out": str(args.out), "summary": report["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
