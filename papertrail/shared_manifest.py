"""Backward-compatible projection of PT run manifests to the shared schema."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN = {"path", "absolute_path", "prompt", "raw_prompt", "full_text",
              "document_text", "api_key", "secret", "token"}


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
    return {
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
