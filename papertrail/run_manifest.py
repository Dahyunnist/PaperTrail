"""Validate public-safe evaluation run manifests and event traces."""
from __future__ import annotations

import re
from typing import Any

EVENT_NAMES = {"retrieval.completed", "rerank.completed", "generation.completed",
               "citation.validated", "access.checked", "human.reviewed"}
FORBIDDEN_KEYS = {"prompt", "raw_prompt", "full_text", "document_text", "api_key", "secret", "token", "path", "absolute_path"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _privacy_issues(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() in FORBIDDEN_KEYS or "secret" in key.casefold() or "api_key" in key.casefold():
                    issues.append(f"forbidden_field:{prefix}{key}")
                walk(child, prefix + key + ".")
        elif isinstance(value, str) and re.search(r"(?:[A-Za-z]:\\|/Users/|/home/|[A-Za-z]:/)", value):
            issues.append(f"private_path:{prefix.rstrip('.')}" )
    walk(row)
    return issues


def validate_manifest(row: dict[str, Any]) -> list[str]:
    required = {"schema_version", "run_id", "trace_id", "git_sha", "dataset_sha256", "prompt_sha256", "scorer_sha256", "split", "runtime", "model_id", "gold_source", "budget", "cost_usd", "status", "started_at", "completed_at"}
    issues = [f"missing:{key}" for key in sorted(required - row.keys())]
    if row.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    for key in ("dataset_sha256", "scorer_sha256"):
        if not isinstance(row.get(key), str) or not SHA256.fullmatch(row[key]):
            issues.append(f"invalid:{key}")
    if row.get("prompt_sha256") is not None and (not isinstance(row["prompt_sha256"], str) or not SHA256.fullmatch(row["prompt_sha256"])):
        issues.append("invalid:prompt_sha256")
    if row.get("cost_usd") is not None and (not isinstance(row["cost_usd"], (int, float)) or row["cost_usd"] < 0):
        issues.append("invalid:cost_usd")
    if row.get("gold_source") != "synthetic_fixture":
        issues.append("synthetic run must declare gold_source=synthetic_fixture")
    if row.get("model_id") is not None:
        issues.append("offline run must declare model_id=null")
    if row.get("cost_usd") is not None:
        issues.append("offline run cost_usd must be null")
    runtime = row.get("runtime")
    if (not isinstance(runtime, dict) or not isinstance(runtime.get("python"), str)
            or not isinstance(runtime.get("platform"), str)
            or not isinstance(runtime.get("lock_sha256"), str)
            or not SHA256.fullmatch(runtime["lock_sha256"])):
        issues.append("runtime provenance missing or invalid")
    if not isinstance(row.get("budget"), dict) or not {"cap_usd", "spent_usd", "status"} <= row["budget"].keys():
        issues.append("budget fields missing")
    issues.extend(_privacy_issues(row))
    return issues


def validate_trace_event(row: dict[str, Any]) -> list[str]:
    issues = []
    for key in ("run_id", "trace_id", "span_id", "event_name", "timestamp"):
        if not row.get(key):
            issues.append(f"missing:{key}")
    if row.get("event_name") not in EVENT_NAMES:
        issues.append("invalid:event_name")
    return issues + _privacy_issues(row)
