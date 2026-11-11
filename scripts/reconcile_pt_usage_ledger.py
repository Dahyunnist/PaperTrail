"""Rebuild a provenance-rich, fail-closed copy of the local model usage ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINAL = ROOT / ".local/pt-master-usage.json"
DEFAULT_BACKUP = ROOT / ".local/pt-master-usage-damaged-20261111.json"
DEFAULT_OUTPUT = ROOT / ".local/pt-master-usage-rebuilt-v2-20261111.json"
HISTORICAL = [
    ROOT / ".local/p6-api-usage.json",
    ROOT / ".local/p12-synthetic-usage.json",
    ROOT / ".local/p13-api-usage.json",
    ROOT / ".local/p13-repeat-api-usage-20261023.json",
]
RATE_INPUT = 0.30
RATE_OUTPUT = 1.32
CAP_USD = 0.50


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _strict_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), _sha256(raw)


def load_damaged_master(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Accept a valid JSON root plus the known two-byte literal `\\n` tail only."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    try:
        data = json.loads(text)
        trailing = b""
    except json.JSONDecodeError:
        data, end = json.JSONDecoder().raw_decode(text)
        trailing = text[end:].encode("utf-8")
        if trailing != b"\\n":
            raise ValueError("damaged ledger has an unrecognized trailing payload")
    if not isinstance(data, dict) or not isinstance(data.get("requests"), list):
        raise ValueError("damaged ledger root must contain a requests list")
    return data, {"sha256": _sha256(raw), "bytes": len(raw),
                  "trailing_bytes_hex": trailing.hex(), "trailing_byte_count": len(trailing)}


def _request_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(key) for key in ("at", "model", "prompt_chars", "prompt_tokens", "completion_tokens"))


def _request_key_hash(key: tuple[Any, ...]) -> str:
    packed = json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _sha256(packed)


def _cost(row: dict[str, Any]) -> float | None:
    prompt_tokens, completion_tokens = row.get("prompt_tokens"), row.get("completion_tokens")
    if (not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool) or prompt_tokens < 0
            or not isinstance(completion_tokens, int) or isinstance(completion_tokens, bool)
            or completion_tokens < 0):
        return None
    return round((prompt_tokens * RATE_INPUT + completion_tokens * RATE_OUTPUT) / 1_000_000, 8)


def _artifact(path: Path, digest: str, role: str) -> dict[str, str]:
    return {"path": _display_path(path), "sha256": digest, "role": role}


def _field(document: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = document
    for part in path:
        value = value[part]
    return value


def _select(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    at = row.get("at")
    if not isinstance(at, str):
        return False
    if "prefixes" in rule:
        return any(at.startswith(prefix) for prefix in rule["prefixes"])
    if "start" in rule:
        return rule["start"] <= at <= rule["end"]
    return False


def _run_rules() -> list[dict[str, Any]]:
    return [
        {"run_id": "PT14", "prefixes": ["2026-10-23T02:15", "2026-10-23T02:16", "2026-10-23T02:17"],
         "report": ROOT / "reports/p14-challenge-20261023.json",
         "call_count_evidence": ROOT / "docs/learning/stage-P14.md", "expected_calls": 64,
         "report_cost_path": ("model_reviewed", "cost_upper_bound_usd"), "report_rate_output": 1.20,
         "historical_cost_source": ".local/p13-repeat-api-usage-20261023.json"},
        {"run_id": "PT9-PT12", "start": "2026-10-23T06:36:44", "end": "2026-10-23T06:42:00",
         "report": ROOT / "evals/pt9-pt12-model-e2e-20261023.json", "expected_calls_path": ("model_usage", "api_calls"),
         "report_cost_path": ("model_usage", "charged_upper_bound_usd"),
         "baseline_path": ("budget_gate", "repriced_spent_upper_bound_usd"),
         "after_path": ("model_usage", "ledger_spent_after_usd")},
        {"run_id": "PT15", "prefixes": ["2026-10-23T07:31"],
         "report": ROOT / "evals/pt15-model-e2e-20261023.json", "prereg": ROOT / "evals/pt15-model-e2e-prereg-20261023.json",
         "expected_calls_path": ("model_usage", "api_calls"), "report_cost_path": ("model_usage", "charged_upper_bound_usd"),
         "baseline_path": ("budget_gate", "master_spent_before_usd"),
         "after_path": ("model_usage", "master_spent_after_usd")},
        {"run_id": "PT16", "prefixes": ["2026-10-23T10:48"],
         "report": ROOT / "evals/pt16-public-probe-20261023.json", "prereg": ROOT / "evals/pt16-public-probe-prereg-20261023.json",
         "expected_calls_path": ("model_calls",), "report_cost_path": ("charged_usd",),
         "baseline_path": ("budget_gate", "master_spent_before_usd"),
         "after_path": ("master_spent_after_usd",)},
        {"run_id": "PT15-supplement", "prefixes": ["2026-10-23T12:31"],
         "report": ROOT / "evals/pt15-supplement-20261023.json", "prereg": ROOT / "evals/pt15-supplement-prereg-20261023.json",
         "expected_calls_path": ("model_usage", "api_calls"), "report_cost_path": ("model_usage", "charged_upper_bound_usd"),
         "baseline_path": ("baseline_spent_usd",), "after_path": ("model_usage", "master_spent_after_usd")},
        {"run_id": "PT17", "prefixes": ["2026-10-23T12:46", "2026-10-23T12:47"],
         "report": ROOT / "evals/pt17-model-e2e-20261023.json", "prereg": ROOT / "evals/pt17-model-e2e-prereg-20261023.json",
         "expected_calls_path": ("model_usage", "api_calls"), "report_cost_path": ("model_usage", "charged_upper_bound_usd"),
         "baseline_path": ("budget_gate", "master_spent_before_usd"),
         "after_path": ("model_usage", "master_spent_after_usd")},
    ]


def rebuild(master: dict[str, Any], master_source: dict[str, Any],
            historical_sources: list[dict[str, Any]], run_rules: list[dict[str, Any]],
            cap_usd: float = CAP_USD) -> dict[str, Any]:
    historical: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for source in historical_sources:
        for index, row in enumerate(source["data"].get("requests", []), 1):
            if not isinstance(row, dict):
                raise ValueError("historical request must be an object")
            historical[_request_key(row)].append({
                "source": source["artifact"]["path"], "source_sha256": source["artifact"]["sha256"],
                "record_index": index, "reported_cost_upper_bound_usd": row.get("cost_upper_bound_usd"),
                "observation_kind": "historical_usage_record",
            })

    master_rows = master["requests"]
    master_by_key: dict[tuple[Any, ...], tuple[int, dict[str, Any]]] = {}
    for index, row in enumerate(master_rows, 1):
        if not isinstance(row, dict):
            raise ValueError("master request must be an object")
        key = _request_key(row)
        if any(key[index] is None for index in (0, 1, 2)) or key in master_by_key:
            raise ValueError("master request identity is missing or duplicated")
        master_by_key[key] = (index, row)

    missing_historical = set(historical) - set(master_by_key)
    if missing_historical:
        raise ValueError(f"master snapshot omits {len(missing_historical)} historical request keys")

    transactions: list[dict[str, Any]] = []
    rule_matches: dict[str, list[dict[str, Any]]] = {rule["run_id"]: [] for rule in run_rules}
    known_source_keys = set(historical)
    unattributed: list[dict[str, Any]] = []
    total = 0.0
    unknown_cost_count = 0
    for key, (master_index, row) in master_by_key.items():
        matching = [rule for rule in run_rules if _select(row, rule)]
        if len(matching) > 1:
            raise ValueError("request matches multiple run attribution windows")
        cost = _cost(row)
        if cost is None:
            unknown_cost_count += 1
        else:
            total += cost
        run_id = matching[0]["run_id"] if matching else ("historical-aggregate" if key in known_source_keys else "unknown")
        observations = list(historical.get(key, []))
        observations.append({
            "source": master_source["artifact"]["path"],
            "source_sha256": master_source["artifact"]["sha256"],
            "record_index": master_index,
            "reported_cost_upper_bound_usd": row.get("cost_upper_bound_usd"),
            "observation_kind": "damaged_master_snapshot",
        })
        transaction = {
            "request_key_sha256": _request_key_hash(key),
            "at": row.get("at"), "model": row.get("model"), "prompt_chars": row.get("prompt_chars"),
            "prompt_tokens": row.get("prompt_tokens"), "completion_tokens": row.get("completion_tokens"),
            "cost_upper_bound_usd": cost,
            "cost_certainty": "estimated_from_recorded_response_usage_peak_price" if cost is not None else "unknown",
            "run_attribution": run_id,
            "source_observations": observations,
            "historical_duplicate_count": max(0, len(historical.get(key, [])) - 1),
        }
        if run_id == "unknown":
            unattributed.append(transaction)
        if run_id in rule_matches:
            rule_matches[run_id].append(transaction)
        transactions.append(transaction)
    total = round(total, 8)

    report_evidence: list[dict[str, Any]] = []
    report_checkpoints: list[tuple[str, float, float]] = []
    checkpoint_issues: list[str] = []
    for rule in run_rules:
        report_data, report_hash = _strict_json(rule["report"])
        matching = rule_matches[rule["run_id"]]
        actual_calls = len(matching)
        expected_calls = rule.get("expected_calls")
        if expected_calls is None:
            expected_calls = int(_field(report_data, rule["expected_calls_path"]))
        if actual_calls != expected_calls:
            checkpoint_issues.append(f"{rule['run_id']}: request count {actual_calls} != report {expected_calls}")

        report_cost = float(_field(report_data, rule["report_cost_path"]))
        if rule.get("historical_cost_source"):
            expected_source = rule["historical_cost_source"]
            source_cost = round(sum(
                float(obs["reported_cost_upper_bound_usd"])
                for transaction in matching
                for obs in transaction["source_observations"]
                if obs["source"] == expected_source
            ), 8)
            if source_cost != round(report_cost, 8):
                checkpoint_issues.append(f"{rule['run_id']}: source usage cost {source_cost} != report {report_cost}")
        else:
            source_cost = round(sum(float(tx["cost_upper_bound_usd"]) for tx in matching
                                    if tx["cost_upper_bound_usd"] is not None), 8)
            if source_cost != round(report_cost, 8):
                checkpoint_issues.append(f"{rule['run_id']}: response usage cost {source_cost} != report {report_cost}")

        after = float(_field(report_data, rule["after_path"])) if rule.get("after_path") else None
        prereg_artifact = None
        if rule.get("prereg"):
            prereg_data, prereg_hash = _strict_json(rule["prereg"])
            prereg_path = rule.get("prereg_baseline_path", rule.get("baseline_path", ("budget_gate", "master_spent_before_usd")))
            baseline = float(_field(prereg_data, prereg_path))
            prereg_artifact = _artifact(rule["prereg"], prereg_hash, "pre_registration")
        else:
            baseline = float(_field(report_data, rule["baseline_path"])) if rule.get("baseline_path") else None
        if baseline is not None and after is not None and round(baseline + report_cost, 8) != round(after, 8):
            checkpoint_issues.append(f"{rule['run_id']}: baseline + report cost != reported after total")
        if baseline is not None and after is not None:
            report_checkpoints.append((rule["run_id"], baseline, after))
        peak_cost = round(sum(float(tx["cost_upper_bound_usd"]) for tx in matching
                              if tx["cost_upper_bound_usd"] is not None), 8)
        report_evidence.append({
            "run_id": rule["run_id"], "report": _artifact(rule["report"], report_hash, "model_run_report"),
            "request_count": actual_calls, "report_cost_upper_bound_usd": report_cost,
            "report_cost_source_basis": "legacy_usage_rate" if rule.get("historical_cost_source") else "report_and_response_usage",
            "ledger_peak_repriced_cost_upper_bound_usd": peak_cost,
            "pre_run_spent_upper_bound_usd": baseline, "post_run_spent_upper_bound_usd": after,
        })
        if prereg_artifact:
            report_evidence[-1]["pre_registration"] = prereg_artifact
        if rule.get("call_count_evidence"):
            evidence_path = rule["call_count_evidence"]
            evidence_bytes = evidence_path.read_bytes()
            report_evidence[-1]["call_count_source"] = _artifact(evidence_path, _sha256(evidence_bytes), "learning_record")

    for previous, current in zip(report_checkpoints, report_checkpoints[1:]):
        if round(previous[2], 8) != round(current[1], 8):
            checkpoint_issues.append(f"{previous[0]} post-run total does not match {current[0]} pre-run total")
    if checkpoint_issues:
        # Report comparisons are repeated here so the top-level state reflects chain validation too.
        checkpoint_status = "mismatch"
    else:
        checkpoint_status = "matched"

    historical_entries = sum(len(source["data"].get("requests", [])) for source in historical_sources)
    historical_unique = len(historical)
    master_only = set(master_by_key) - known_source_keys
    duplicate_count = historical_entries - historical_unique
    unattributed_cost = round(sum(float(tx["cost_upper_bound_usd"]) for tx in unattributed
                                  if tx["cost_upper_bound_usd"] is not None), 8)
    master_only_costs = [_cost(master_by_key[key][1]) for key in master_only]
    historical_unique_costs = [_cost(master_by_key[key][1]) for key in known_source_keys]
    remaining = round(cap_usd - total, 8) if unknown_cost_count == 0 else None
    block_reasons = []
    if unknown_cost_count:
        block_reasons.append("unknown_response_usage_cost")
    if unattributed:
        block_reasons.append("unattributed_master_snapshot_requests")
    if checkpoint_issues:
        block_reasons.append("report_reconciliation_mismatch")
    return {
        "schema_version": 2,
        "ledger_id": "PT-master-reconciled-v2-20261111",
        "status": "blocked" if block_reasons else "reconciled",
        "model_calls_allowed": not block_reasons,
        "block_reasons": block_reasons,
        "cap_usd": cap_usd,
        "spent_upper_bound_usd": total if unknown_cost_count == 0 else None,
        "known_spent_upper_bound_usd": total,
        "unknown_cost_count": unknown_cost_count,
        "unknown_cost_usd": 0.0 if unknown_cost_count == 0 else None,
        "remaining_upper_bound_usd": remaining,
        "spendable_balance_usd": remaining if not block_reasons else 0.0,
        "unattributed_request_count": len(unattributed),
        "unattributed_upper_bound_usd": unattributed_cost,
        "pricing_basis": {
            "model": "deepseek-flash", "input_usd_per_million_tokens": RATE_INPUT,
            "output_usd_per_million_tokens": RATE_OUTPUT,
            "method": "prompt_tokens * input_rate + completion_tokens * output_rate; rounded per request to 8 decimals",
            "certainty": "estimated upper bound from recorded response usage; not invoice-confirmed",
        },
        "reconciliation": {
            "master_raw_sha256": master_source["artifact"]["sha256"],
            "master_bytes": master_source["recovery"]["bytes"],
            "master_trailing_bytes_hex": master_source["recovery"]["trailing_bytes_hex"],
            "master_trailing_byte_count": master_source["recovery"]["trailing_byte_count"],
            "historical_observations": historical_entries,
            "historical_unique_requests": historical_unique,
            "duplicate_historical_observations_not_counted": duplicate_count,
            "master_snapshot_requests": len(master_by_key),
            "master_snapshot_unique_keys": len(master_by_key),
            "master_requests_matching_history": len(set(master_by_key) & known_source_keys),
            "master_only_requests": len(master_only),
            "master_only_upper_bound_usd": (None if any(value is None for value in master_only_costs)
                                            else round(sum(master_only_costs), 8)),
            "historical_unique_repriced_upper_bound_usd": (
                None if any(value is None for value in historical_unique_costs)
                else round(sum(historical_unique_costs), 8)),
            "report_checkpoint_status": checkpoint_status,
            "report_checkpoint_issues": checkpoint_issues,
        },
        "source_artifacts": [source["artifact"] for source in historical_sources] + [master_source["artifact"]],
        "report_evidence": report_evidence,
        # Keep requests compatible with local_llm's budget reader. Do not install while blocked.
        "requests": transactions,
    }


def load_sources(master_path: Path, historical_paths: list[Path], run_rules: list[dict[str, Any]]
                 ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    master, recovery = load_damaged_master(master_path)
    master_source = {"data": master, "recovery": recovery,
                     "artifact": _artifact(master_path, recovery["sha256"], "damaged_master_snapshot")}
    historical_sources = []
    for path in historical_paths:
        data, digest = _strict_json(path)
        historical_sources.append({"data": data, "artifact": _artifact(path, digest, "historical_response_usage_ledger")})
    for rule in run_rules:
        rule["report"] = Path(rule["report"])
        if rule.get("prereg"):
            rule["prereg"] = Path(rule["prereg"])
        if rule.get("call_count_evidence"):
            rule["call_count_evidence"] = Path(rule["call_count_evidence"])
    return master, master_source, historical_sources


def rebuild_from_files(master_path: Path, historical_paths: list[Path], cap_usd: float = CAP_USD
                       ) -> dict[str, Any]:
    master, recovery = load_damaged_master(master_path)
    master_source = {"data": master, "recovery": recovery,
                     "artifact": _artifact(master_path, recovery["sha256"], "damaged_master_snapshot")}
    historical_sources = []
    for path in historical_paths:
        data, digest = _strict_json(path)
        historical_sources.append({"data": data, "artifact": _artifact(path, digest, "historical_response_usage_ledger")})
    return rebuild(master, master_source, historical_sources, _run_rules(), cap_usd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--historical", nargs="+", type=Path, default=HISTORICAL)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output already exists; refusing overwrite")
    original_hash = _sha256(args.original.read_bytes())
    backup_hash = _sha256(args.backup.read_bytes())
    if original_hash != backup_hash:
        raise SystemExit("read-only backup does not match original ledger hash")
    ledger = rebuild_from_files(args.backup, args.historical)
    ledger["reconciliation"]["original_path_sha256"] = original_hash
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".partial")
    try:
        temp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(args.output)
    finally:
        temp.unlink(missing_ok=True)
    print(json.dumps({"output": _display_path(args.output), "status": ledger["status"],
                      "model_calls_allowed": ledger["model_calls_allowed"],
                      "requests": len(ledger["requests"]),
                      "spent_upper_bound_usd": ledger["spent_upper_bound_usd"],
                      "remaining_upper_bound_usd": ledger["remaining_upper_bound_usd"],
                      "unattributed_request_count": ledger["unattributed_request_count"],
                      "report_checkpoint_status": ledger["reconciliation"]["report_checkpoint_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
