"""One-time, cost-gated QA probe over one registered public CC BY paper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail import qa
from papertrail.local_llm import _max_request_cost
from papertrail.qa import _validate_quote, ask
from papertrail.s1_index import index_selection, open_database

MANIFEST = ROOT / "evals/pt10-public-source-manifest-20261023.json"
MASTER_LEDGER = ROOT / ".local/pt-master-usage.json"
WORK = ROOT / ".local/pt16-public-probe"
DATABASE = WORK / "probe.sqlite3"
SELECTION = WORK / "selection.jsonl"
SOURCES = WORK / "sources.yaml"
REPORT = ROOT / "evals/pt16-public-probe-20261023.json"
PAPER_DOI = "10.1371/journal.pcbi.1005510"
QUESTION = "Where should researchers put input data versus files produced during analysis?"
EXPECTED_PAGES = (10,)
EXPECTED_FACETS = ("raw data and metadata belong in a data directory",
                   "files generated during cleanup and analysis belong in a results directory",
                   "generated files include intermediate and final results")
STAGE_CAP_USD = 0.04
CALL_LIMIT = 8
REQUEST_MAX_CHARS = 2_400
OUTPUT_MAX_TOKENS = 800
RESERVE_PER_REQUEST = _max_request_cost(REQUEST_MAX_CHARS)
MODEL_ENVELOPE_USD = round(CALL_LIMIT * RESERVE_PER_REQUEST, 8)
WRAPUP_BUFFER_USD = round(STAGE_CAP_USD - MODEL_ENVELOPE_USD, 8)
MINIMUM_REMAINING_USD = 0.06643472


def _ledger() -> dict[str, Any]:
    if not MASTER_LEDGER.is_file():
        raise RuntimeError("主费用账本不存在")
    data = json.loads(MASTER_LEDGER.read_text(encoding="utf-8"))
    if data.get("cap_usd") != 0.5:
        raise RuntimeError("主账本总上限不是 $0.50")
    return data


def _source() -> tuple[dict[str, Any], Path]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    matches = [row for row in manifest["sources"] if row.get("doi") == PAPER_DOI]
    if len(matches) != 1:
        raise RuntimeError("公开论文登记中 DOI 不唯一")
    paper = matches[0]
    paper_license = paper.get("license", manifest.get("license"))
    if paper_license != "CC BY 4.0":
        raise RuntimeError("仅允许明确登记为 CC BY 4.0 的论文")
    paper["license"] = paper_license
    source = (ROOT / paper["local_pdf"]).resolve()
    if not source.is_file():
        raise RuntimeError("登记的开放许可 PDF 不存在")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != paper.get("local_pdf_sha256"):
        raise RuntimeError("开放论文 PDF 哈希与许可登记不符")
    return paper, source


def _prepare() -> tuple[dict[str, Any], Path, dict[str, Any]]:
    paper, source = _source()
    WORK.mkdir(parents=True, exist_ok=True)
    SELECTION.write_text(json.dumps({
        "root_id": "pt16_public_probe", "file_name": source.name,
        "relative_path": source.name, "sha256": paper["local_pdf_sha256"],
        "kind": "pdf", "source_type": "original_pdf",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    SOURCES.write_text("roots:\n  - id: pt16_public_probe\n    path: " +
                       json.dumps(str(source.parent), ensure_ascii=False) + "\n", encoding="utf-8")
    if not DATABASE.exists():
        indexed = index_selection(DATABASE, SOURCES, SELECTION)
        if indexed.get("added") != 1 or indexed.get("issues"):
            raise RuntimeError(f"开放论文导入失败：{indexed}")
    conn = open_database(DATABASE, readonly=True)
    try:
        rows = [dict(row) for row in conn.execute(
            "SELECT v.sha256,c.page_number,l.absolute_path FROM chunks c "
            "JOIN paper_versions v ON v.version_id=c.version_id "
            "JOIN source_locations l ON l.version_id=v.version_id "
            "WHERE c.source_type='original_pdf' GROUP BY c.chunk_id")]
    finally:
        conn.close()
    if not rows or {row["sha256"] for row in rows} != {paper["local_pdf_sha256"]}:
        raise RuntimeError("单篇论文索引包含空索引或额外来源")
    return paper, source, {"indexed_chunks": len(rows),
                           "database_sha256": hashlib.sha256(DATABASE.read_bytes()).hexdigest()}


def _offline_evidence(source: Path, expected_hash: str) -> list[dict[str, Any]]:
    result = ask(DATABASE, QUESTION, limit=1, mode="bm25", generate=False)
    evidence = [claim["evidence"] for claim in result["claims"]]
    if not evidence:
        raise RuntimeError("无模型检索未得到可核验片段；未调用模型")
    cache: dict[tuple[str, int, str], str] = {}
    for item in evidence:
        if item["sha256"] != expected_hash or not _validate_quote(
                str(source), expected_hash, item["pdf_page"], item["quote"], cache):
            raise RuntimeError("检索片段来源校验失败；未调用模型")
    return evidence


def _dry_run() -> None:
    paper, source, index_info = _prepare()
    evidence = _offline_evidence(source, paper["local_pdf_sha256"])
    ledger = _ledger()
    remaining = round(float(ledger["cap_usd"]) - float(ledger["spent_upper_bound_usd"]), 8)
    preflight = {
        "dataset_role": "one_question_public_paper_probe",
        "doi": PAPER_DOI, "license": paper["license"], "question": QUESTION,
        "expected_pages": list(EXPECTED_PAGES), "expected_oracle_facets": list(EXPECTED_FACETS),
        "retrieved_evidence": [{key: item[key] for key in ("title", "sha256", "pdf_page", "quote")}
                               for item in evidence],
        "index": index_info, "model": "deepseek-flash",
        "request_bound": {"max_calls_including_retries": CALL_LIMIT,
                          "max_prompt_chars_each": REQUEST_MAX_CHARS,
                          "max_output_tokens_each": OUTPUT_MAX_TOKENS,
                          "peak_cost_each_usd": RESERVE_PER_REQUEST,
                          "model_envelope_usd": MODEL_ENVELOPE_USD,
                          "wrapup_buffer_usd": WRAPUP_BUFFER_USD,
                          "total_stage_cap_usd": STAGE_CAP_USD},
        "ledger_before_usd": {"spent": ledger["spent_upper_bound_usd"],
                              "remaining": remaining},
        "minimum_remaining_required_usd": MINIMUM_REMAINING_USD,
        "model_calls": 0,
    }
    if remaining < STAGE_CAP_USD or remaining < MINIMUM_REMAINING_USD:
        raise RuntimeError(f"剩余费用不足，未调用模型：{remaining}")
    print(json.dumps(preflight, ensure_ascii=True, indent=2))


def _run_once() -> None:
    if REPORT.exists():
        raise RuntimeError("一次性结果文件已存在；拒绝重复模型评测")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("缺少 DeepSeek API 凭据；未调用模型")
    paper, source, index_info = _prepare()
    evidence = _offline_evidence(source, paper["local_pdf_sha256"])
    ledger = _ledger()
    baseline = float(ledger["spent_upper_bound_usd"])
    remaining = float(ledger["cap_usd"]) - baseline
    if remaining < MINIMUM_REMAINING_USD or remaining < STAGE_CAP_USD:
        raise RuntimeError("费用余额未达到调用门槛；未调用模型")

    os.environ["PAPERTRAIL_LLM_PROVIDER"] = "openai-compatible"
    os.environ["PAPERTRAIL_LLM_MODEL"] = "deepseek-flash"
    os.environ["PAPERTRAIL_OPENAI_BASE_URL"] = "https://api.deepseek.com"
    os.environ["PAPERTRAIL_LLM_BUDGET_FILE"] = str(MASTER_LEDGER)
    os.environ["PAPERTRAIL_LLM_BUDGET_USD"] = "0.50"
    os.environ["PAPERTRAIL_RETRIEVAL_MODE"] = "bm25"
    os.environ["PAPERTRAIL_EVIDENCE_LIMIT"] = "1"
    real_chat_json = qa.chat_json
    active_reserve = 0.0
    calls = 0

    def budgeted_chat_json(model: str, system: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal active_reserve, calls
        request_chars = len(system) + len(prompt) + len("\nReturn a valid JSON object only.")
        if request_chars > REQUEST_MAX_CHARS:
            raise RuntimeError("预登记 prompt 长度上限将被超过；请求未发送")
        next_reserve = _max_request_cost(request_chars)
        current = _ledger()
        charged = float(current["spent_upper_bound_usd"]) - baseline
        if calls >= CALL_LIMIT or max(charged, active_reserve) + next_reserve > MODEL_ENVELOPE_USD:
            raise RuntimeError("单题费用预留将超 $0.031488；请求未发送")
        if float(current["spent_upper_bound_usd"]) + next_reserve > float(current["cap_usd"]):
            raise RuntimeError("总账费用上限将被超过；请求未发送")
        active_reserve = round(active_reserve + next_reserve, 8)
        calls += 1
        return real_chat_json(model, system, prompt, **kwargs)

    qa.chat_json = budgeted_chat_json
    failure = None
    result = None
    try:
        result = ask(DATABASE, QUESTION, limit=1, mode="bm25", generate=True)
    except Exception as exc:
        failure = f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        qa.chat_json = real_chat_json

    after = _ledger()
    citations = [claim["evidence"] for claim in (result or {}).get("claims", [])]
    page_cache: dict[tuple[str, int, str], str] = {}
    citation_checks = []
    for citation in citations:
        citation_checks.append({
            "sha256_matches": citation["sha256"] == paper["local_pdf_sha256"],
            "expected_page_matches": citation["pdf_page"] in EXPECTED_PAGES,
            "quote_in_pdf_page": _validate_quote(str(source), citation["sha256"],
                                                   citation["pdf_page"], citation["quote"], page_cache),
            "quote": citation["quote"], "page": citation["pdf_page"],
        })
    report = {
        "schema_version": 1, "dataset_role": "one_question_public_paper_probe",
        "status": "completed" if result and not failure else "incomplete",
        "doi": PAPER_DOI, "title": paper["title"], "license": paper["license"],
        "license_evidence": paper["license_evidence"], "license_detail": paper["license_detail"],
        "source_pdf_sha256": paper["local_pdf_sha256"], "question": QUESTION,
        "oracle": {"expected_pages": list(EXPECTED_PAGES),
                   "expected_facets": list(EXPECTED_FACETS),
                   "review_status": "pending_manual_oracle_review",
                   "semantic_claims": [claim["text"] for claim in (result or {}).get("claims", [])],
                   "claim_support_review": "See report notes; model self-judgment is not independent."},
        "claims": [{"text": claim["text"], "support": claim.get("support"),
                    "evidence": claim["evidence"]}
                   for claim in (result or {}).get("claims", [])],
        "citation_checks": citation_checks,
        "all_citations_hash_page_quote_valid": bool(citation_checks) and all(
            row["sha256_matches"] and row["quote_in_pdf_page"] for row in citation_checks),
        "model": "deepseek-flash", "model_calls": calls,
        "reserved_usd": round(active_reserve, 8),
        "stage_cap_usd": STAGE_CAP_USD,
        "charged_usd": round(float(after["spent_upper_bound_usd"]) - baseline, 8),
        "master_spent_after_usd": after["spent_upper_bound_usd"],
        "master_remaining_after_usd": round(float(after["cap_usd"]) -
                                               float(after["spent_upper_bound_usd"]), 8),
        "index": index_info, "failure": failure,
        "limitations": ["单篇开放许可论文的单题探针，不是基准分数或泛化结论。",
                        "模型内置审查与回答同源，不是独立语义审阅。",
                        "引用支持需按报告中人工核验 oracle 逐条检查。"],
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(REPORT), "status": report["status"],
                      "model_calls": calls, "reserved_usd": report["reserved_usd"],
                      "charged_usd": report["charged_usd"],
                      "master_remaining_after_usd": report["master_remaining_after_usd"],
                      "failure": failure}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", help="send one real generation QA turn")
    args = parser.parse_args()
    if args.run_once:
        _run_once()
    else:
        _dry_run()


if __name__ == "__main__":
    main()
