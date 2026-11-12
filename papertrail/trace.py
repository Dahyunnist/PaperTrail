"""Opt-in, content-free JSONL trace events."""
from __future__ import annotations

import contextvars
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_context: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar("papertrail_trace", default=None)
_lock = threading.Lock()
_ALLOWED = {
    "retrieval.completed": {"mode", "result_count", "status"},
    "rerank.completed": {"method", "candidate_count", "result_count", "status"},
    "generation.completed": {"model_id", "status"},
    "citation.validated": {"source_sha256", "page", "valid"},
    "access.checked": {"operation", "allowed", "principal_hash"},
    "human.reviewed": {"label", "evidence_id_hash"},
}


def trace_context() -> tuple[str, str]:
    current = _context.get()
    return current if current else (str(uuid.uuid4()), str(uuid.uuid4()))


def bind_trace() -> contextvars.Token:
    return _context.set((str(uuid.uuid4()), str(uuid.uuid4())))


def reset_trace(token: contextvars.Token) -> None:
    _context.reset(token)


def emit(event_name: str, **attributes: Any) -> None:
    path = os.environ.get("PAPERTRAIL_TRACE_JSONL")
    if not path or event_name not in _ALLOWED:
        return
    run_id, trace_id = trace_context()
    safe = {key: value for key, value in attributes.items()
            if key in _ALLOWED[event_name] and isinstance(value, (str, int, float, bool, type(None)))}
    row = {"run_id": run_id, "trace_id": trace_id, "span_id": str(uuid.uuid4()),
           "event_name": event_name, "timestamp": datetime.now(timezone.utc).isoformat(), **safe}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock, target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
