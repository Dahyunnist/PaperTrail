"""Local learning workspace storage, uploaded-PDF lifecycle, and reporting."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .s1_index import open_database


def ensure_workspace_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS user_uploads (
        upload_id TEXT PRIMARY KEY, version_id TEXT, sha256 TEXT NOT NULL,
        original_name TEXT NOT NULL, stored_path TEXT NOT NULL,
        state TEXT NOT NULL, issue TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS personal_notes (
        note_id TEXT PRIMARY KEY, concept TEXT NOT NULL, body TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_notes_updated ON personal_notes(updated_at DESC);
    """)
    from .qa import _ensure_qa_schema
    from .compare import _ensure_schema as ensure_comparison_schema
    _ensure_qa_schema(conn)
    ensure_comparison_schema(conn)


def create_note(database: Path, concept: str, body: str) -> dict[str, Any]:
    concept, body = concept.strip(), body.strip()
    if not concept or not body:
        raise ValueError("笔记概念和内容都不能为空")
    now, note_id = datetime.now(timezone.utc).isoformat(), str(uuid.uuid4())
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        conn.execute("INSERT INTO personal_notes VALUES(?,?,?,?,?)",
                     (note_id, concept, body, now, now))
        conn.commit()
        return {"note_id": note_id, "concept": concept, "body": body,
                "created_at": now, "updated_at": now}
    finally:
        conn.close()


def search_notes(database: Path, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        if query.strip():
            needle = f"%{query.strip()}%"
            rows = conn.execute("SELECT * FROM personal_notes WHERE concept LIKE ? OR body LIKE ? "
                                "ORDER BY updated_at DESC LIMIT ?", (needle, needle, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM personal_notes ORDER BY updated_at DESC LIMIT ?",
                                (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_note(database: Path, note_id: str) -> bool:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        cursor = conn.execute("DELETE FROM personal_notes WHERE note_id=?", (note_id,))
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def library_documents(database: Path) -> list[dict[str, Any]]:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        rows = conn.execute(
            "SELECT v.version_id,v.sha256,v.source_type,v.file_name,v.page_count,v.parseable_pages,"
            "v.low_text_pages_json,v.parse_status,v.parser_version,p.paper_id,p.title_candidate,"
            "GROUP_CONCAT(DISTINCT l.root_id) AS source_roots "
            "FROM paper_versions v JOIN papers p ON p.paper_id=v.paper_id "
            "LEFT JOIN source_locations l ON l.version_id=v.version_id "
            "GROUP BY v.version_id ORDER BY p.title_candidate,v.indexed_at DESC").fetchall()
        return [{**dict(row), "low_text_pages": json.loads(row["low_text_pages_json"]),
                 "source_roots": (row["source_roots"] or "").split(",")}
                for row in rows]
    finally:
        conn.close()


def register_upload(database: Path, upload_id: str, sha256: str, original_name: str,
                    stored_path: Path, state: str = "processing", issue: str = "",
                    version_id: str | None = None) -> None:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        conn.execute("INSERT INTO user_uploads VALUES(?,?,?,?,?,?,?,?)",
                     (upload_id, version_id, sha256, original_name, str(stored_path), state,
                      issue, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()


def update_upload(database: Path, upload_id: str, state: str, issue: str = "",
                  version_id: str | None = None) -> None:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        conn.execute("UPDATE user_uploads SET state=?,issue=?,version_id=COALESCE(?,version_id) WHERE upload_id=?",
                     (state, issue, version_id, upload_id))
        conn.commit()
    finally:
        conn.close()


def list_uploads(database: Path) -> list[dict[str, Any]]:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        return [dict(row) for row in conn.execute("SELECT * FROM user_uploads ORDER BY created_at DESC")]
    finally:
        conn.close()


def remove_upload(database: Path, upload_id: str, upload_root: Path) -> bool:
    root = upload_root.resolve()
    conn = open_database(database)
    source_to_remove: Path | None = None
    try:
        ensure_workspace_schema(conn)
        upload = conn.execute("SELECT * FROM user_uploads WHERE upload_id=?", (upload_id,)).fetchone()
        if upload is None:
            return False
        source_to_remove = Path(upload["stored_path"]).resolve()
        if not source_to_remove.is_relative_to(root):
            raise ValueError("上传文件路径不在应用管理的个人资料目录中")
        with conn:
            if upload["version_id"]:
                conn.execute("DELETE FROM source_locations WHERE version_id=? AND absolute_path=?",
                             (upload["version_id"], str(source_to_remove)))
                remaining = conn.execute("SELECT COUNT(*) FROM source_locations WHERE version_id=?",
                                         (upload["version_id"],)).fetchone()[0]
                if not remaining:
                    chunk_ids = [row[0] for row in conn.execute(
                        "SELECT chunk_id FROM chunks WHERE version_id=?", (upload["version_id"],))]
                    conn.executemany("DELETE FROM chunks_fts WHERE chunk_id=?",
                                     ((chunk_id,) for chunk_id in chunk_ids))
                    paper_id = conn.execute("SELECT paper_id FROM paper_versions WHERE version_id=?",
                                            (upload["version_id"],)).fetchone()
                    conn.execute("DELETE FROM paper_versions WHERE version_id=?", (upload["version_id"],))
                    if paper_id and not conn.execute("SELECT 1 FROM paper_versions WHERE paper_id=?",
                                                     (paper_id[0],)).fetchone():
                        conn.execute("DELETE FROM papers WHERE paper_id=?", (paper_id[0],))
                    conn.execute("UPDATE app_metadata SET value=CAST(value AS INTEGER)+1 WHERE key='index_revision'")
            conn.execute("DELETE FROM user_uploads WHERE upload_id=?", (upload_id,))
        if source_to_remove.is_file():
            source_to_remove.unlink()
        return True
    finally:
        conn.close()


def dashboard_stats(database: Path) -> dict[str, Any]:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        summary = {
            "documents": conn.execute("SELECT COUNT(*) FROM paper_versions").fetchone()[0],
            "indexed_chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "questions": conn.execute("SELECT COUNT(*) FROM qa_turns").fetchone()[0],
            "conversations": conn.execute("SELECT COUNT(*) FROM qa_conversations").fetchone()[0],
            "personal_notes": conn.execute("SELECT COUNT(*) FROM personal_notes").fetchone()[0],
            "comparisons": conn.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0],
            "pending_uploads": conn.execute("SELECT COUNT(*) FROM user_uploads WHERE state IN ('processing','failed','needs_attention')").fetchone()[0],
            "ocr_pages": conn.execute("SELECT COALESCE(SUM(json_array_length(ocr_pages_json)),0) FROM paper_versions").fetchone()[0],
            "low_text_pages": sum(len(json.loads(row[0])) for row in conn.execute(
                "SELECT low_text_pages_json FROM paper_versions")),
        }
        return summary
    finally:
        conn.close()


def study_report(database: Path) -> dict[str, Any]:
    conn = open_database(database)
    try:
        ensure_workspace_schema(conn)
        docs = [{k: row[k] for k in ("paper_id", "version_id", "sha256", "source_type",
                                      "file_name", "page_count", "parseable_pages", "parse_status")}
                for row in conn.execute("SELECT p.paper_id,v.version_id,v.sha256,v.source_type,v.file_name,"
                    "v.page_count,v.parseable_pages,v.parse_status FROM paper_versions v "
                    "JOIN papers p ON p.paper_id=v.paper_id ORDER BY p.title_candidate")]
        conversations = []
        for turn in conn.execute("SELECT * FROM qa_turns ORDER BY created_at"):
            claims = []
            for row in conn.execute("SELECT claim_text,evidence_json FROM qa_claims WHERE turn_id=? ORDER BY ordinal",
                                    (turn["turn_id"],)):
                citation = json.loads(row["evidence_json"])
                citation.pop("path", None)
                claims.append({"claim": row["claim_text"], "evidence": citation})
            conversations.append({"turn_id": turn["turn_id"], "conversation_id": turn["conversation_id"],
                                  "question": turn["question"], "answer": turn["answer"],
                                  "status": turn["status"], "created_at": turn["created_at"],
                                  "claims": claims})
        notes = [dict(row) for row in conn.execute("SELECT concept,body,created_at,updated_at FROM personal_notes ORDER BY updated_at DESC")]
        comparisons = []
        for comparison in conn.execute("SELECT * FROM comparisons ORDER BY created_at"):
            evidence = []
            for row in conn.execute("SELECT * FROM comparison_evidence WHERE comparison_id=? ORDER BY ordinal",
                                    (comparison["comparison_id"],)):
                item = dict(row)
                item.pop("path", None)
                evidence.append(item)
            gaps = [dict(row) for row in conn.execute("SELECT * FROM comparison_gaps WHERE comparison_id=?",
                                                      (comparison["comparison_id"],))]
            for gap in gaps:
                gap["basis_evidence_ids"] = json.loads(gap.pop("basis_evidence_json"))
            comparisons.append({**dict(comparison), "evidence": evidence, "gap_candidates": gaps})
        return {"generated_at": datetime.now(timezone.utc).isoformat(),
                "progress": dashboard_stats(database), "documents": docs,
                "question_turns": conversations, "personal_notes": notes,
                "comparisons": comparisons}
    finally:
        conn.close()
