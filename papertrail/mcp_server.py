"""Read-only MCP stdio server for PaperTrail evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .s1_index import search

SERVER_INFO = {"name": "papertrail", "version": "0.1.0"}
TOOLS = [
    {"name": "search_papers", "description": "Search indexed original papers. Returns document and page pointers.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "minLength": 1}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
         "required": ["query"], "additionalProperties": False}},
    {"name": "get_evidence", "description": "Read one PDF page after verifying the source file SHA-256.",
     "inputSchema": {"type": "object", "properties": {
         "sha256": {"type": "string", "pattern": "^[a-fA-F0-9]{64}$"},
         "page": {"type": "integer", "minimum": 1}},
         "required": ["sha256", "page"], "additionalProperties": False}},
]


def _database() -> Path:
    raw = os.environ.get("PAPERTRAIL_DB")
    if not raw:
        raise ValueError("PAPERTRAIL_DB must point to an existing indexed database")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise ValueError("indexed database does not exist")
    return path


def _readonly(database: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _document_path(database: Path, sha256: str) -> tuple[dict[str, Any], Path] | None:
    conn = _readonly(database)
    try:
        row = conn.execute("SELECT v.version_id,v.sha256,v.parse_status,v.page_count,p.title_candidate "
                           "FROM paper_versions v JOIN papers p ON p.paper_id=v.paper_id "
                           "WHERE v.sha256=? AND v.source_type='original_pdf'", (sha256,)).fetchone()
        if not row:
            return None
        location = conn.execute("SELECT absolute_path FROM source_locations WHERE version_id=? LIMIT 1",
                                (row["version_id"],)).fetchone()
        if not location:
            return None
        return dict(row), Path(location["absolute_path"])
    finally:
        conn.close()


def get_evidence(database: Path, sha256: str, page_number: int) -> dict[str, Any]:
    if (not isinstance(sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", sha256)
            or not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1):
        raise ValueError("invalid SHA-256 or page")
    match = _document_path(database, sha256.lower())
    if not match:
        raise ValueError("original paper not found")
    metadata, path = match
    if not path.is_file():
        raise ValueError("source file changed or is unavailable")
    with path.open("rb") as stream:
        actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual_hash != sha256.lower():
        raise ValueError("source file changed or is unavailable")
    import fitz
    with fitz.open(path) as doc:
        if page_number > doc.page_count:
            raise ValueError("page is outside source document")
        text = doc[page_number - 1].get_text("text")
    return {"sha256": sha256.lower(), "page": page_number, "title": metadata["title_candidate"],
            "text": text, "text_origin": "native_pdf_page"}


def _resource_list(database: Path) -> list[dict[str, Any]]:
    conn = _readonly(database)
    try:
        rows = conn.execute("SELECT v.sha256,v.page_count,p.title_candidate FROM paper_versions v "
                            "JOIN papers p ON p.paper_id=v.paper_id WHERE v.source_type='original_pdf' "
                            "ORDER BY p.title_candidate").fetchall()
        return [{"uri": f"papertrail://documents/{row['sha256']}", "name": row["title_candidate"],
                 "description": f"Original PDF metadata; {row['page_count']} pages",
                 "mimeType": "application/json"} for row in rows]
    finally:
        conn.close()


def _resource_read(database: Path, uri: str) -> dict[str, Any]:
    parsed = urlparse(uri)
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme != "papertrail" or parsed.netloc not in {"documents", "evidence"}:
        raise ValueError("unknown resource URI")
    if parsed.netloc == "evidence" and len(parts) == 2 and parts[1].isdigit():
        value = get_evidence(database, parts[0], int(parts[1]))
    elif parsed.netloc == "documents" and len(parts) == 1 and re.fullmatch(r"[a-fA-F0-9]{64}", parts[0]):
        match = _document_path(database, parts[0].lower())
        if not match:
            raise ValueError("original paper not found")
        metadata, _ = match
        value = {"sha256": metadata["sha256"], "title": metadata["title_candidate"],
                 "page_count": metadata["page_count"], "parse_status": metadata["parse_status"]}
    else:
        raise ValueError("malformed resource URI")
    return {"contents": [{"uri": uri, "mimeType": "application/json" if "title" in value else "text/plain",
                           "text": json.dumps(value, ensure_ascii=False)}]}


def _call(database: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    if name == "search_papers":
        if set(arguments) - {"query", "limit"}:
            raise ValueError("unknown search_papers argument")
        query = arguments.get("query")
        limit = arguments.get("limit", 5)
        if not isinstance(query, str) or not query.strip() or not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("query and limit do not match tool schema")
        hits = search(database, query, limit=limit, source_type="original_pdf", readonly=True)
        safe = [{"title": row["title"], "sha256": row["sha256"], "page": row["pdf_page"],
                 "section": row["section"], "score": row["rank_score"], "chunk_id": row["chunk_id"]}
                for row in hits]
        return {"content": [{"type": "text", "text": json.dumps(safe, ensure_ascii=False)}],
                "structuredContent": {"results": safe}}
    if name == "get_evidence":
        if set(arguments) != {"sha256", "page"}:
            raise ValueError("get_evidence requires sha256 and page only")
        value = get_evidence(database, arguments.get("sha256", ""), arguments.get("page", 0))
        return {"content": [{"type": "text", "text": value["text"]}], "structuredContent": value}
    raise ValueError("unknown tool")


def handle(database: Path, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {})
    if method == "notifications/initialized":
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion", "2025-11-25"),
                      "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}},
                      "serverInfo": SERVER_INFO}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                result = _call(database, params.get("name", ""), params.get("arguments", {}))
            except (ValueError, OSError, sqlite3.Error) as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        elif method == "resources/list":
            result = {"resources": _resource_list(database)}
        elif method == "resources/read":
            result = _resource_read(database, params.get("uri", ""))
        else:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"}}
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (ValueError, OSError, sqlite3.Error) as exc:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32602, "message": str(exc)}}


def main(database_path: Path | None = None) -> None:
    try:
        database = database_path.resolve() if database_path else _database()
        if not database.is_file():
            raise ValueError("indexed database does not exist")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle(database, request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {type(exc).__name__}"}}
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
