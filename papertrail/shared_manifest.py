"""Backward-compatible projection of PT run manifests to the shared schema."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{64}$")
_SHARED_REQUIRED = {
    "schema_version", "project", "git_sha", "dataset_id", "dataset_sha256", "split",
    "model_id", "prompt_sha", "tool_schema_sha", "runtime_digest", "max_steps",
    "max_tokens", "scorer_sha", "gold_source", "cost_usd_estimate", "run_id",
    "trace_id", "span_id", "started_at", "ended_at", "status", "budget", "field_status",
}
_FIELD_STATES = {"recorded", "not_applicable", "not_recorded", "blocked"}
_FORBIDDEN = {"path", "absolute_path", "prompt", "raw_prompt", "full_text",
              "document_text", "api_key", "secret", "token"}
_PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|private)/)", re.IGNORECASE)


def _is_observed_zero_usage(value: Any) -> bool:
    return (isinstance(value, dict)
            and set(value) == {"request_count", "response_count", "cost_usd_estimate", "status"}
            and type(value["request_count"]) is int and value["request_count"] == 0
            and type(value["response_count"]) is int and value["response_count"] == 0
            and isinstance(value["cost_usd_estimate"], (int, float))
            and not isinstance(value["cost_usd_estimate"], bool)
            and value["cost_usd_estimate"] == 0
            and value["status"] == "observed_zero_requests")


def _reject_private(value: Any, location: str = "manifest") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key).casefold()
            if name in _FORBIDDEN or "api_key" in name or "secret" in name:
                raise ValueError(f"private field rejected: {location}.{key}")
            _reject_private(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private(child, f"{location}[{index}]")
    elif isinstance(value, str) and _PRIVATE_PATH.search(value):
        raise ValueError(f"private path value rejected: {location}")


def validate_shared_manifest(value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or _SHARED_REQUIRED - value.keys():
        raise ValueError("shared manifest required fields missing")
    if value.keys() - _SHARED_REQUIRED:
        raise ValueError("shared manifest has unsupported fields")
    _reject_private(value)
    for key in ("dataset_sha256", "scorer_sha"):
        if not isinstance(value[key], str) or not _SHA.fullmatch(value[key]):
            raise ValueError(f"{key} invalid")
    for key in ("prompt_sha", "tool_schema_sha", "runtime_digest"):
        if value[key] is not None and (not isinstance(value[key], str) or not _SHA.fullmatch(value[key])):
            raise ValueError(f"{key} invalid")
    cost = value["cost_usd_estimate"]
    if cost is not None and (not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0):
        raise ValueError("cost_usd_estimate invalid")
    if value["status"] not in {"passed", "failed", "blocked"}:
        raise ValueError("status invalid")
    try:
        start = datetime.fromisoformat(value["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(value["ended_at"].replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("timestamps invalid") from exc
    if start.tzinfo is None or end.tzinfo is None or end < start:
        raise ValueError("timestamp order invalid")
    if value["schema_version"] != 1 or value["project"] != "PaperTrail":
        raise ValueError("manifest identity invalid")
    if not isinstance(value["field_status"], dict):
        raise ValueError("field_status invalid")
    if not isinstance(value["budget"], dict):
        raise ValueError("budget invalid")
    for key in ("project", "dataset_id", "split", "model_id", "run_id", "trace_id"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"{key} invalid")
    if value["gold_source"] is not None and (
            not isinstance(value["gold_source"], str) or not value["gold_source"].strip()):
        raise ValueError("gold_source invalid")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(value["git_sha"])):
        raise ValueError("git_sha invalid")
    if value["span_id"] is not None and (not isinstance(value["span_id"], str) or not value["span_id"].strip()):
        raise ValueError("span_id invalid")
    for key, minimum in (("max_steps", 0), ("max_tokens", 1)):
        if value[key] is not None and (not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < minimum):
            raise ValueError(f"{key} invalid")
    nullable = {key for key, item in value.items() if item is None and key != "field_status"}
    if nullable - value["field_status"].keys():
        raise ValueError("null field status missing")
    for key, state in value["field_status"].items():
        if key not in value or state not in _FIELD_STATES:
            raise ValueError(f"{key} field status invalid")
        if (value[key] is None) != (state != "recorded"):
            raise ValueError(f"{key} field status mismatch")
    for key in nullable:
        if value["field_status"].get(key) not in _FIELD_STATES:
            raise ValueError(f"{key} null requires field status")


def to_shared_manifest_v1(pt_manifest: dict[str, Any]) -> dict[str, Any]:
    """Project existing PT metadata; absent or inapplicable values remain null."""
    if not isinstance(pt_manifest, dict):
        raise ValueError("PT manifest must be an object")
    _reject_private(pt_manifest)
    runtime = pt_manifest.get("runtime")
    runtime_digest = None
    if isinstance(runtime, dict):
        lock_hash = runtime.get("lock_sha256")
        if lock_hash is not None and (not isinstance(lock_hash, str) or not _SHA.fullmatch(lock_hash)):
            raise ValueError("runtime lock_sha256 is invalid")
        if lock_hash:
            runtime_digest = hashlib.sha256(json.dumps(runtime, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()
    model_id = pt_manifest.get("model_id") or "none"
    dataset_sha256 = pt_manifest.get("dataset_sha256")
    result = {
        "schema_version": 1,
        "project": "PaperTrail",
        "git_sha": pt_manifest.get("git_sha"),
        "dataset_id": pt_manifest.get("dataset_id") or (f"sha256:{dataset_sha256}" if dataset_sha256 else None),
        "dataset_sha256": dataset_sha256,
        "split": pt_manifest.get("split"),
        "model_id": model_id,
        "prompt_sha": pt_manifest.get("prompt_sha", pt_manifest.get("prompt_sha256")),
        "tool_schema_sha": pt_manifest.get("tool_schema_sha"),
        "runtime_digest": runtime_digest,
        "max_steps": pt_manifest.get("max_steps"),
        "max_tokens": pt_manifest.get("max_tokens"),
        "scorer_sha": pt_manifest.get("scorer_sha", pt_manifest.get("scorer_sha256")),
        "gold_source": pt_manifest.get("gold_source"),
        "cost_usd_estimate": pt_manifest.get("cost_usd", pt_manifest.get("cost_usd_estimate")),
        "run_id": pt_manifest.get("run_id"),
        "trace_id": pt_manifest.get("trace_id"),
        "span_id": pt_manifest.get("span_id"),
        "started_at": pt_manifest.get("started_at"),
        "ended_at": pt_manifest.get("ended_at", pt_manifest.get("completed_at")),
        "status": pt_manifest.get("status"),
        "budget": pt_manifest.get("budget"),
        "field_status": {},
    }
    if result["model_id"] == "none" and result["cost_usd_estimate"] is None:
        result["cost_usd_estimate"] = 0
    result["field_status"] = {}
    not_applicable_without_model = {
        "prompt_sha", "tool_schema_sha", "runtime_digest", "max_steps", "max_tokens"
    }
    for key, field_value in result.items():
        if key == "field_status":
            continue
        if field_value is None:
            state = ("not_applicable" if key in not_applicable_without_model
                     and result["model_id"] == "none" else "not_recorded")
            result["field_status"][key] = state
    for key in ("prompt_sha", "tool_schema_sha", "runtime_digest", "max_steps", "max_tokens"):
        result["field_status"].setdefault(key, "recorded" if result[key] is not None else "not_applicable")
    result["field_status"].setdefault("span_id", "not_recorded" if result["span_id"] is None else "recorded")
    result["field_status"].setdefault("cost_usd_estimate", "not_recorded" if result["cost_usd_estimate"] is None else "recorded")
    result["field_status"].setdefault("budget", "not_recorded" if result["budget"] is None else "recorded")
    validate_shared_manifest(result)
    return result


def to_shared_manifest(pt_manifest: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible name for the v1 projection."""
    return to_shared_manifest_v1(pt_manifest)


def to_shared_manifest_v2(pt_manifest: dict[str, Any]) -> dict[str, Any]:
    """Project explicit request/response usage, preserving unknown usage as null."""
    base = to_shared_manifest_v1(pt_manifest)
    usage = pt_manifest.get("usage")
    if usage is not None:
        if not _is_observed_zero_usage(usage):
            raise ValueError("usage must be explicit observed_zero_requests or null")
        usage = dict(usage)
    result = {**base, "schema_version": 2, "usage": usage}
    result["field_status"] = dict(base["field_status"])
    if usage is None and pt_manifest.get("cost_usd") is None and pt_manifest.get("cost_usd_estimate") is None:
        result["cost_usd_estimate"] = None
        result["field_status"]["cost_usd_estimate"] = "not_recorded"
    result["field_status"]["usage"] = "recorded" if usage is not None else "not_recorded"
    validate_shared_manifest_v2(result)
    return result


def validate_shared_manifest_v2(value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or "usage" not in value:
        raise ValueError("shared manifest v2 usage missing")
    base = dict(value)
    base.pop("usage")
    base["schema_version"] = 1
    base["field_status"] = dict(base.get("field_status", {}))
    base["field_status"].pop("usage", None)
    validate_shared_manifest(base)
    usage = value["usage"]
    if usage is not None and not _is_observed_zero_usage(usage):
        raise ValueError("usage invalid")
    if value["schema_version"] != 2:
        raise ValueError("manifest v2 identity invalid")
    state = value["field_status"].get("usage")
    if state != ("recorded" if usage is not None else "not_recorded"):
        raise ValueError("usage field status mismatch")
