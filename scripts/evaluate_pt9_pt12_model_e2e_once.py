"""Run the preregistered PT9/PT12 model evaluation once, under the master cost cap."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import papertrail.qa as qa
from papertrail.local_llm import _max_request_cost


REPORT = ROOT / "evals" / "pt9-pt12-model-e2e-20261023.json"
GOLD = ROOT / "evals" / "pt9-pt12-final-heldout-gold-20261023.jsonl"
DATABASE = ROOT / ".local" / "pt-public-all-20261023.sqlite3"
LEDGER = ROOT / ".local" / "pt-master-usage.json"
RUN_RESERVE_USD = 0.075
MODEL = "deepseek-flash"
SOURCE_HASHES = {
    "papertrail/qa.py": "016c248b59c71e577c70d9b5c7849c6ce22645c486a90e14aaba66fb506e37ad",
    "papertrail/local_llm.py": "bd634caf59099971ee361ac5e8e81316c9553c287ec1d04844cf374aecd1503f",
    "papertrail/retrieval.py": "568a0c5fc42f63a830293d73fc03513d9fe1c99edb3151881bec817556be151c",
    "papertrail/s1_index.py": "5178d49744232b8226b82edea1dd92cb9ab481e354a924fccf5f12a8c03b96d1",
    "papertrail/templates/index.html": "3eb93c4e160f71e1b7cdc98d99e3271560a4d25170b0f470a235988cb96e2017",
}


class EvaluationReserveExceeded(Exception):
    """Stop this single run before sending a request that exceeds its reserve."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _evidence_rows(claim: dict[str, Any]) -> list[dict[str, Any]]:
    primary = claim.get("evidence") or {}
    rows = [primary] + list(primary.get("support_evidence") or [])
    unique = []
    seen = set()
    for row in rows:
        key = (row.get("sha256"), row.get("pdf_page"), row.get("quote"))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _check_preregistration(report: dict[str, Any]) -> None:
    if report.get("status") != "preregistered_not_run":
        raise SystemExit("评测已经启动或完成；冻结组禁止重跑")
    gold_sha = _sha256(GOLD)
    database_sha = _sha256(DATABASE)
    if gold_sha != report["gold_sha256"] or database_sha != report["database_sha256"]:
        raise SystemExit("冻结题集或数据库哈希与预登记不符")
    for relative, expected in SOURCE_HASHES.items():
        if _sha256(ROOT / relative) != expected:
            raise SystemExit(f"锁定代码已变化：{relative}")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    remaining = float(ledger["cap_usd"]) - float(ledger["spent_upper_bound_usd"])
    if remaining < RUN_RESERVE_USD:
        raise SystemExit(f"账本余量不足：需 ${RUN_RESERVE_USD:.6f}，现余 ${remaining:.8f}")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("缺少 DeepSeek API 凭据；冻结组不调用模型")


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    _check_preregistration(report)
    before = json.loads(LEDGER.read_text(encoding="utf-8"))
    before_cost = float(before["spent_upper_bound_usd"])

    report["status"] = "started"
    report["started_at"] = datetime.now(timezone.utc).isoformat()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    os.environ["PAPERTRAIL_LLM_PROVIDER"] = "openai-compatible"
    os.environ["PAPERTRAIL_LLM_MODEL"] = MODEL
    os.environ["PAPERTRAIL_OPENAI_BASE_URL"] = "https://api.deepseek.com"
    os.environ["PAPERTRAIL_LLM_BUDGET_FILE"] = str(LEDGER)
    os.environ["PAPERTRAIL_LLM_BUDGET_USD"] = "0.50"
    os.environ["PAPERTRAIL_RETRIEVAL_MODE"] = "bm25"
    os.environ["PAPERTRAIL_EVIDENCE_LIMIT"] = "5"

    real_chat_json = qa.chat_json
    reserved = 0.0
    calls = 0

    def budgeted_chat_json(model: str, system: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal reserved, calls
        next_reserve = _max_request_cost(len(system) + len(prompt) + len("\nReturn a valid JSON object only."))
        if reserved + next_reserve > RUN_RESERVE_USD:
            raise EvaluationReserveExceeded(
                f"运行预留上限 ${RUN_RESERVE_USD:.3f} 将被超出；新请求未发送")
        reserved = round(reserved + next_reserve, 8)
        calls += 1
        return real_chat_json(model, system, prompt, **kwargs)

    qa.chat_json = budgeted_chat_json
    gold_rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines()]
    completed = []
    failure = None
    try:
        for item in gold_rows:
            result = qa.ask(DATABASE, item["question"], limit=5, mode="bm25", generate=True)
            cited = [row for claim in result["claims"] for row in _evidence_rows(claim)]
            gold_page_hits = 0
            phrase_hits = 0
            exact_hits = 0
            for gold_evidence in item["evidence"]:
                matching = [row for row in cited if row.get("sha256") == gold_evidence["sha256"]
                            and row.get("pdf_page") == gold_evidence["pdf_page"]]
                gold_page_hits += int(bool(matching))
                gold_phrase = _norm(gold_evidence["quote"])
                phrase_hits += int(any(gold_phrase in _norm(row.get("quote", "")) for row in matching))
                exact_hits += int(any(gold_phrase == _norm(row.get("quote", "")) for row in matching))
            completed.append({
                "id": item["id"], "question_type": item["question_type"],
                "gold_abstain": item["abstain"], "status": result["status"],
                "model_claims": [claim["text"] for claim in result["claims"]],
                "coverage_complete": result["coverage_complete"],
                "coverage_gaps": result["coverage_gaps"],
                "gold_evidence_pages": len(item["evidence"]),
                "gold_pages_cited": gold_page_hits,
                "gold_phrases_contained": phrase_hits,
                "exact_gold_quotes": exact_hits,
                "cited_evidence": [{"title": row.get("title"), "pdf_page": row.get("pdf_page"),
                                    "sha256": row.get("sha256"), "quote": row.get("quote")}
                                   for row in cited],
                "turn_model_calls": result["model_budget"]["calls"],
                "turn_reserved_usd": result["model_budget"]["reserved_usd"],
                "usage": result.get("usage"),
            })
    except EvaluationReserveExceeded as exc:
        failure = str(exc)
    except Exception as exc:
        failure = f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        qa.chat_json = real_chat_json

    after = json.loads(LEDGER.read_text(encoding="utf-8"))
    charged = round(float(after["spent_upper_bound_usd"]) - before_cost, 8)
    pages_total = sum(len(item["evidence"]) for item in gold_rows if not item["abstain"])
    result_totals = {
        "questions_completed": len(completed), "questions_total": len(gold_rows),
        "answerable_questions": sum(not item["abstain"] for item in gold_rows),
        "unanswerable_questions": sum(item["abstain"] for item in gold_rows),
        "answerable_gold_pages": pages_total,
        "gold_pages_cited": sum(row["gold_pages_cited"] for row in completed),
        "gold_phrases_contained": sum(row["gold_phrases_contained"] for row in completed),
        "exact_gold_quotes": sum(row["exact_gold_quotes"] for row in completed),
        "generated_claims": sum(len(row["model_claims"]) for row in completed),
        "unanswerable_abstentions": sum(row["gold_abstain"] and row["status"] == "abstained"
                                         for row in completed),
    }
    report.update({
        "status": "completed_once_no_tuning_after" if len(completed) == len(gold_rows)
                  and failure is None else "incomplete_once_no_rerun",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "model_usage": {"api_calls": calls, "reserved_usd": round(reserved, 8),
                        "charged_upper_bound_usd": charged,
                        "ledger_spent_after_usd": after["spent_upper_bound_usd"],
                        "ledger_remaining_after_usd": round(
                            float(after["cap_usd"]) - float(after["spent_upper_bound_usd"]), 8),
                        "run_reserve_ceiling_usd": RUN_RESERVE_USD},
        "totals": result_totals,
        "results": completed,
        "failure": failure,
    })
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "totals": result_totals,
                      "model_usage": report["model_usage"], "failure": failure},
                     ensure_ascii=False, indent=2))
    if failure:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
