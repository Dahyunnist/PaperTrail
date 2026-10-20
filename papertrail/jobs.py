"""Durable, single-process background index queue."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_EVENTS: dict[str, threading.Event] = {}
_THREADS: dict[str, threading.Thread] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""CREATE TABLE IF NOT EXISTS index_jobs (
        job_id TEXT PRIMARY KEY, state TEXT NOT NULL, payload_json TEXT NOT NULL,
        progress_json TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    return conn


def recover_jobs(database: Path) -> int:
    with _connect(database) as conn:
        cursor = conn.execute("UPDATE index_jobs SET state='queued',updated_at=? WHERE state='running'", (_now(),))
        return cursor.rowcount


def enqueue_index(database: Path, sources: Path, selection: Path,
                  upload_id: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    payload = {"sources": str(sources.resolve()), "selection": str(selection.resolve()),
               "upload_id": upload_id}
    with _connect(database) as conn:
        conn.execute("INSERT INTO index_jobs VALUES(?,?,?,?,0,NULL,?,?)",
                     (job_id, "queued", json.dumps(payload), json.dumps({"completed": 0, "total": 0}), _now(), _now()))
    _wake(database)
    return job_id


def get_job(database: Path, job_id: str) -> dict[str, Any] | None:
    with _connect(database) as conn:
        row = conn.execute("SELECT * FROM index_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["progress"] = json.loads(item.pop("progress_json"))
    item.pop("payload_json", None)
    return item


def recent_jobs(database: Path, limit: int = 10) -> list[dict[str, Any]]:
    with _connect(database) as conn:
        ids = [row[0] for row in conn.execute("SELECT job_id FROM index_jobs ORDER BY created_at DESC LIMIT ?", (limit,))]
    return [job for job_id in ids if (job := get_job(database, job_id))]


def _wake(database: Path) -> None:
    key = str(database.resolve())
    with _LOCK:
        event = _EVENTS.setdefault(key, threading.Event())
        event.set()
        thread = _THREADS.get(key)
        if thread and thread.is_alive():
            return
        thread = threading.Thread(target=_run, args=(database, event), daemon=True,
                                  name=f"papertrail-index-{database.stem}")
        _THREADS[key] = thread
        thread.start()


def _run(database: Path, event: threading.Event) -> None:
    key = str(database.resolve())
    recover_jobs(database)
    while True:
        event.clear()
        with _connect(database) as conn:
            row = conn.execute("SELECT * FROM index_jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE index_jobs SET state='running',attempts=attempts+1,updated_at=? WHERE job_id=?",
                             (_now(), row["job_id"]))
        if not row:
            event.wait()
            continue
        job_id = row["job_id"]
        payload = json.loads(row["payload_json"])
        try:
            from .s1_index import index_selection, inspect_document
            from .workspace import update_upload

            def progress(done: int, total: int, current: str) -> None:
                with _connect(database) as conn:
                    conn.execute("UPDATE index_jobs SET progress_json=?,updated_at=? WHERE job_id=?",
                                 (json.dumps({"completed": done, "total": total, "current": current}, ensure_ascii=False),
                                  _now(), job_id))

            result = index_selection(Path(database), Path(payload["sources"]), Path(payload["selection"]),
                                     progress_callback=progress)
            issues = result.get("issues", [])
            state = "succeeded" if not issues else "succeeded_with_issues"
            error = json.dumps(issues, ensure_ascii=False) if issues else None
            if payload.get("upload_id"):
                upload_id = payload["upload_id"]
                upload = _upload_row(database, upload_id)
                version = inspect_document(database, upload["sha256"][:16]) if upload else None
                upload_state = "indexed" if version and not issues else "needs_attention"
                update_upload(database, upload_id, upload_state, error or "",
                              version["version_id"] if version else None)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if row["attempts"] < 2:
                state = "queued"
            else:
                state = "failed"
        with _connect(database) as conn:
            conn.execute("UPDATE index_jobs SET state=?,error=?,updated_at=? WHERE job_id=?",
                         (state, error, _now(), job_id))
        if state == "queued":
            event.set()
        if payload.get("upload_id"):
            Path(payload["sources"]).unlink(missing_ok=True)
            Path(payload["selection"]).unlink(missing_ok=True)


def _upload_row(database: Path, upload_id: str) -> dict[str, Any] | None:
    # Upload schemas are owned by workspace; query only after it initialized the table.
    with _connect(database) as conn:
        try:
            row = conn.execute("SELECT sha256 FROM uploads WHERE upload_id=?", (upload_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
    return dict(row) if row else None
