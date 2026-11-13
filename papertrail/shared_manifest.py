"""Backward-compatible projection of PT run manifests to the shared schema."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN = {"path", "absolute_path", "prompt", "raw_prompt", "full_text",
              "document_text", "api_key", "secret", "token"}
_PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|private)/)", re.IGNORECASE)


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
    required = {"schema_version", "project", "git_sha", "dataset_id", "dataset_sha256", "split",
                "model_id", "prompt_sha", "tool_schema_sha", "runtime_digest", "max_steps",
                "max_tokens", "scorer_sha", "gold_source", "cost_usd_estimate", "run_id",
                "trace_id", "span_id", "started_at", "ended_at", "status", "budget"}
    if not isinstance(value, dict) or required - value.keys():
        raise ValueError("shared manifest required fields missing")
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
    if value["schema_version"] != 1 or value["project"] != "papertrail":
        raise ValueError("manifest identity invalid")


def to_shared_manifest(pt_manifest: dict[str, Any]) -> dict[str, Any]:
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
    result = {
        "schema_version": 1,
        "project": "papertrail",
        "git_sha": pt_manifest.get("git_sha"),
        "dataset_id": pt_manifest.get("dataset_id"),
        "dataset_sha256": pt_manifest.get("dataset_sha256"),
        "split": pt_manifest.get("split"),
        "model_id": pt_manifest.get("model_id"),
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
    }
    validate_shared_manifest(result)
    return result
