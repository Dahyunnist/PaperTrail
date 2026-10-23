"""Run the frozen PT15 paper-disjoint holdout once under the master budget."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail import qa
from papertrail.local_llm import _max_request_cost
from papertrail.qa import _validate_quote

PREREG = ROOT / "evals" / "pt15-model-e2e-prereg-20261023.json"
OUTPUT = ROOT / "evals" / "pt15-model-e2e-20261023.json"
GOLD = ROOT / "evals" / "pt15-heldout-gold-20261023.jsonl"
DATABASE = ROOT / ".local" / "pt15-heldout.sqlite3"
LEDGER = ROOT / ".local" / "pt-master-usage.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prompt_sha256() -> str:
    names = ("_plan_subquestions", "_screen_evidence", "_synthesize_local", "_hosted_json_prompt")
    payload = "\n".join(f"{name}\n{inspect.getsource(getattr(qa, name))}" for name in names)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evidence_rows(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for claim in claims:
        values = [claim.get("evidence"), *(claim.get("support_evidence") or [])]
        for row in values:
            if not isinstance(row, dict):
                continue
            key = (row.get("sha256", ""), row.get("pdf_page", 0), row.get("quote", ""))
            if key not in seen:
                seen.add(key)
                output.append(row)
    return output


def _score_result(item: dict[str, Any], result: dict[str, Any], source_paths: dict[str, Path]) -> dict[str, Any]:
    cited = _evidence_rows(result["claims"])
    verified = []
    page_hits = phrase_hits = exact_hits = 0
    page_cache: dict[tuple[str, int, str], str] = {}
    for row in cited:
        path = source_paths.get(row.get("sha256", ""))
        valid = bool(path and _validate_quote(str(path), row["sha256"], row["pdf_page"],
                                             row.get("quote", ""), page_cache))
        verified.append(valid)
    for gold in item["evidence"]:
        matches = [row for row in cited if row.get("sha256") == gold["sha256"]
                   and row.get("pdf_page") == gold["pdf_page"]]
        page_hits += int(bool(matches))
        normalize = qa._normalize_excerpt
        phrase = normalize(gold["quote"])
        phrase_hits += int(any(phrase in normalize(row.get("quote", "")) for row in matches))
        exact_hits += int(any(phrase == normalize(row.get("quote", "")) for row in matches))
    return {
        "gold_evidence_pages": len(item["evidence"]),
        "gold_pages_cited": page_hits,
        "gold_phrases_contained": phrase_hits,
        "exact_gold_quotes": exact_hits,
        "displayed_citations": len(cited),
        "all_displayed_citations_source_valid": all(verified) if verified else None,
        "citation_validation_results": verified,
    }


def main() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg["status"] != "preregistered_not_run":
        raise SystemExit("PT15 预登记状态不允许本次调用")
    if OUTPUT.exists():
        raise SystemExit("PT15 结果文件已存在；禁止重复评测")
    if _sha256(GOLD) != prereg["gold_sha256"] or _sha256(DATABASE) != prereg["database_sha256"]:
        raise SystemExit("PT15 题集或索引库哈希与冻结值不符")
    if _sha256(Path(__file__)) != prereg["locked_hashes"]["runner_sha256"]:
        raise SystemExit("PT15 评测器代码哈希与冻结值不符")
    if _prompt_sha256() != prereg["locked_hashes"]["prompt_sha256"]:
        raise SystemExit("QA 提示词源哈希与冻结值不符")
    artifact_hashes = {
        "evals/pt15-heldout-source-manifest-20261023.json": "source_manifest_sha256",
        "evals/pt15-heldout-sources.yaml": "source_config_sha256",
        "evals/pt15-heldout-selection.jsonl": "selection_sha256",
    }
    for relative, key in artifact_hashes.items():
        if _sha256(ROOT / relative) != prereg["locked_hashes"][key]:
            raise SystemExit(f"已锁定评测资料变化：{relative}")
    for relative, expected in prereg["locked_hashes"]["source_code"].items():
        if _sha256(ROOT / relative) != expected:
            raise SystemExit(f"已锁定代码变化：{relative}")
    source_paths: dict[str, Path] = {}
    for source in prereg["sources"]:
        path = ROOT / source["local_pdf"]
        if _sha256(path) != source["local_pdf_sha256"]:
            raise SystemExit(f"来源 PDF 哈希变化：{source['file_name']}")
        source_paths[source["local_pdf_sha256"]] = path

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    baseline = float(ledger["spent_upper_bound_usd"])
    gate = prereg["budget_gate"]
    cap = float(ledger["cap_usd"])
    if baseline != gate["master_spent_before_usd"] or cap != gate["master_cap_usd"]:
        raise SystemExit("总账与预登记预算起点不符")
    reserve_cap = float(gate["evaluation_peak_reserve_cap_usd"])
    if reserve_cap >= gate["master_remaining_before_usd"]:
        raise SystemExit("本次峰值预留必须小于总账余量")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("缺少 DeepSeek API 凭据；未调用模型")

    os.environ["PAPERTRAIL_LLM_PROVIDER"] = "openai-compatible"
    os.environ["PAPERTRAIL_LLM_MODEL"] = prereg["locked_config"]["model"]
    os.environ["PAPERTRAIL_OPENAI_BASE_URL"] = prereg["locked_config"]["base_url"]
    os.environ["PAPERTRAIL_LLM_BUDGET_FILE"] = str(LEDGER)
    os.environ["PAPERTRAIL_LLM_BUDGET_USD"] = str(cap)
    os.environ["PAPERTRAIL_RETRIEVAL_MODE"] = prereg["locked_config"]["retrieval_mode"]
    os.environ["PAPERTRAIL_EVIDENCE_LIMIT"] = str(prereg["locked_config"]["evidence_limit"])

    real_chat_json = qa.chat_json
    reserved = 0.0
    calls = 0
    active_reserve = 0.0

    def budgeted_chat_json(model: str, system: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal reserved, calls, active_reserve
        next_reserve = _max_request_cost(len(system) + len(prompt) + len("\nReturn a valid JSON object only."))
        current = json.loads(LEDGER.read_text(encoding="utf-8"))
        charged = float(current["spent_upper_bound_usd"]) - baseline
        if max(charged, reserved) + next_reserve > reserve_cap:
            raise RuntimeError("PT15 单次评测峰值预留上限将被超过；请求未发送")
        if float(current["spent_upper_bound_usd"]) + next_reserve > cap:
            raise RuntimeError("总账 `$0.50` 上限将被超过；请求未发送")
        reserved = round(reserved + next_reserve, 8)
        active_reserve = round(active_reserve + next_reserve, 8)
        calls += 1
        return real_chat_json(model, system, prompt, **kwargs)

    qa.chat_json = budgeted_chat_json
    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    results: list[dict[str, Any]] = []
    failure = None
    try:
        for item in rows:
            start_calls, start_reserve = calls, active_reserve
            result = qa.ask(DATABASE, item["question"],
                            limit=prereg["locked_config"]["evidence_limit"],
                            mode=prereg["locked_config"]["retrieval_mode"], generate=True)
            results.append({
                "id": item["id"], "question_type": item["question_type"],
                "gold_abstain": item["abstain"], "status": result["status"],
                "model_claims": [claim["text"] for claim in result["claims"]],
                "coverage_complete": result["coverage_complete"],
                "coverage_gaps": result["coverage_gaps"],
                **_score_result(item, result, source_paths),
                "qa_diagnostics": (result.get("usage") or {}).get("_diagnostics", {}),
                "turn_model_calls": calls - start_calls,
                "turn_reserved_usd": round(active_reserve - start_reserve, 8),
                "usage": result.get("usage"),
            })
            diagnostics = (result.get("usage") or {}).get("_diagnostics", {})
            call_error = diagnostics.get("synthesis_error") or diagnostics.get("planning_error")
            if isinstance(call_error, str) and any(token in call_error.casefold()
                                                   for token in ("budget", "上限", "未发送")):
                failure = f"预算保护拦截请求：{call_error[:180]}"
                break
    except Exception as exc:
        failure = f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        qa.chat_json = real_chat_json

    after = json.loads(LEDGER.read_text(encoding="utf-8"))
    charged = round(float(after["spent_upper_bound_usd"]) - baseline, 8)
    metrics = {
        "questions_completed": len(results), "questions_total": len(rows),
        "answerable_questions": sum(not item["abstain"] for item in rows),
        "unanswerable_questions": sum(item["abstain"] for item in rows),
        "gold_evidence_pages": sum(row["gold_evidence_pages"] for row in results),
        "gold_pages_cited": sum(row["gold_pages_cited"] for row in results),
        "gold_phrases_contained": sum(row["gold_phrases_contained"] for row in results),
        "exact_gold_quotes": sum(row["exact_gold_quotes"] for row in results),
        "generated_claims": sum(len(row["model_claims"]) for row in results),
        "unanswerable_abstentions": sum(row["gold_abstain"] and row["status"] == "abstained"
                                         for row in results),
        "all_displayed_citations_source_valid": all(
            row["all_displayed_citations_source_valid"] for row in results
            if row["displayed_citations"]),
    }
    report = {
        "schema_version": 1,
        "status": "completed_once_human_review_pending" if len(results) == len(rows) and not failure
                  else "incomplete_once_human_review_pending",
        "dataset_role": "final_paper_disjoint_holdout",
        "preregistration": PREREG.name,
        "gold_sha256": prereg["gold_sha256"],
        "database_sha256": prereg["database_sha256"],
        "locked_config": prereg["locked_config"],
        "metrics": metrics,
        "human_review": {"status": "pending_independent_human_review",
                         "same_model_support_review_is_not_independent": True},
        "model_usage": {"api_calls": calls, "summed_request_reserves_usd": reserved,
                        "charged_upper_bound_usd": charged,
                        "master_spent_after_usd": after["spent_upper_bound_usd"],
                        "master_remaining_after_usd": round(cap - float(after["spent_upper_bound_usd"]), 8),
                        "evaluation_peak_reserve_cap_usd": reserve_cap},
        "failure": failure,
        "results": results,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "status": report["status"], "metrics": metrics,
                      "model_usage": report["model_usage"], "failure": failure}, ensure_ascii=False, indent=2))
    if failure or len(results) != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
