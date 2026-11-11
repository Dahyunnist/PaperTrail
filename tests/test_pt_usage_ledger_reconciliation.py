import importlib.util
import ast
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reconcile_pt_usage_ledger", ROOT / "scripts/reconcile_pt_usage_ledger.py"
)
reconcile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reconcile)


def _source(path, rows):
    return {"data": {"requests": rows}, "artifact": {"path": path, "sha256": "a" * 64}}


def _row(at="2026-10-23T00:00:00Z", prompt_tokens=10, completion_tokens=5):
    return {"at": at, "model": "deepseek-flash", "prompt_chars": 20,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "cost_upper_bound_usd": 0.000009}


def test_historical_duplicate_observations_count_once():
    row = _row()
    second = _row(at="2026-10-23T00:00:01Z", prompt_tokens=20, completion_tokens=10)
    ledger = reconcile.rebuild(
        {"requests": [row, second]}, {**_source("master", []), "recovery": {"bytes": 10, "trailing_bytes_hex": "5c6e", "trailing_byte_count": 2}},
        [_source("old-a", [row, second]), _source("old-b", [row])], [], cap_usd=1.0,
    )
    assert len(ledger["requests"]) == 2
    assert ledger["requests"][0]["historical_duplicate_count"] == 1
    assert ledger["known_spent_upper_bound_usd"] == sum(
        request["cost_upper_bound_usd"] for request in ledger["requests"]
    )
    assert ledger["reconciliation"]["duplicate_historical_observations_not_counted"] == 1


def test_unattributed_request_blocks_calls_and_spendable_balance():
    ledger = reconcile.rebuild(
        {"requests": [_row()]}, {**_source("master", []), "recovery": {"bytes": 10, "trailing_bytes_hex": "5c6e", "trailing_byte_count": 2}}, [], [], cap_usd=1.0,
    )
    assert ledger["status"] == "blocked"
    assert ledger["model_calls_allowed"] is False
    assert ledger["unattributed_request_count"] == 1
    assert ledger["spendable_balance_usd"] == 0


def test_unknown_usage_cost_blocks_and_keeps_total_unknown():
    row = _row(prompt_tokens=None)
    ledger = reconcile.rebuild(
        {"requests": [row]}, {**_source("master", []), "recovery": {"bytes": 10, "trailing_bytes_hex": "5c6e", "trailing_byte_count": 2}}, [], [], cap_usd=1.0,
    )
    assert ledger["unknown_cost_count"] == 1
    assert ledger["spent_upper_bound_usd"] is None
    assert ledger["remaining_upper_bound_usd"] is None
    assert ledger["model_calls_allowed"] is False
    assert ledger["requests"][0]["cost_upper_bound_usd"] is None


def test_damaged_master_accepts_only_known_literal_suffix(tmp_path):
    damaged = tmp_path / "damaged.json"
    damaged.write_bytes(b'{"requests": []}\\n')
    data, recovery = reconcile.load_damaged_master(damaged)
    assert data == {"requests": []}
    assert recovery["trailing_bytes_hex"] == "5c6e"
    damaged.write_bytes(b'{"requests": []}\\nx')
    with pytest.raises(ValueError, match="unrecognized trailing payload"):
        reconcile.load_damaged_master(damaged)


def test_v2_schema_requires_fail_closed_budget_fields():
    schema = json.loads((ROOT / "evals/pt-usage-ledger-v2.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {"model_calls_allowed", "spendable_balance_usd", "unknown_cost_count", "requests"} <= required
    assert schema["properties"]["schema_version"]["const"] == 2
    assert schema["properties"]["spent_upper_bound_usd"]["type"] == ["number", "null"]
    request = schema["$defs"]["request"]["properties"]
    assert request["cost_upper_bound_usd"]["type"] == ["number", "null"]


def test_pt1_csv_import_path_has_no_network_capability():
    paths = [
        "scripts/import_pt1_human_csv.py", "scripts/import_pt1_gold_jsonl.py",
        "scripts/validate_pt1_gold_jsonl.py", "papertrail/gold.py",
    ]
    forbidden = {"requests", "httpx", "urllib", "socket", "aiohttp", "websocket"}
    for rel in paths:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
        imports = set()
        network_names = set()
        url_literals = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Name):
                network_names.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                network_names.add(node.attr.lower())
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                url_literals.append(node.value.lower())
        assert not (imports & forbidden), f"network import in {rel}"
        assert not (network_names & {"urlopen", "request", "requests", "connect", "create_connection"}), f"network call in {rel}"
        assert not any(value.startswith(("http://", "https://")) for value in url_literals), f"network URL in {rel}"


def test_blocked_rebuilt_ledger_stops_before_hosted_request(monkeypatch):
    import papertrail.local_llm as llm

    path = ROOT / ".tmp/pt-blocked-ledger-test.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"schema_version": 2, "model_calls_allowed": False,
                               "spent_upper_bound_usd": 0.1}), encoding="utf-8")
    monkeypatch.setenv("PAPERTRAIL_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("PAPERTRAIL_LLM_BUDGET_FILE", str(path))
    monkeypatch.setattr(llm, "urlopen", lambda *_args, **_kwargs: pytest.fail("network call attempted"))
    try:
        with pytest.raises(RuntimeError, match="ledger blocks model calls"):
            llm.chat_json("deepseek-flash", "system", "prompt")
    finally:
        path.unlink(missing_ok=True)
