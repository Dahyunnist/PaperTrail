"""Single-user local read-only MCP stdio server; no caller authentication is provided."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .access import (LOCAL_PRINCIPAL, Principal, _source_matches_sha, document_metadata,
                     read_evidence, search_papers)
from .s1_index import open_database

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


def get_evidence(database: Path, sha256: str, page_number: int,
                 principal: Principal = LOCAL_PRINCIPAL) -> dict[str, Any]:
    return read_evidence(database, sha256, page_number, principal)


def _resource_list(database: Path, principal: Principal = LOCAL_PRINCIPAL) -> list[dict[str, Any]]:
    conn = _readonly(database)
    try:
        rows = conn.execute("SELECT v.sha256,v.page_count,p.title_candidate,l.absolute_path FROM paper_versions v "
                            "JOIN papers p ON p.paper_id=v.paper_id "
                            "JOIN source_locations l ON l.version_id=v.version_id "
                            "JOIN collections col ON col.collection_id=v.collection_id "
                            "WHERE v.source_type='original_pdf' AND col.owner_id=? "
                            "ORDER BY p.title_candidate", (principal.user_id,)).fetchall()
    finally:
        conn.close()
    resources = []
    seen: set[str] = set()
    for row in rows:
        digest = row["sha256"]
        if digest in seen or not _source_matches_sha(Path(row["absolute_path"]), digest):
            continue
        seen.add(digest)
        resources.append({"uri": f"papertrail://documents/{digest}", "name": row["title_candidate"],
                          "description": f"Original PDF metadata; {row['page_count']} pages",
                          "mimeType": "application/json"})
    return resources


def _resource_read(database: Path, uri: str, principal: Principal = LOCAL_PRINCIPAL) -> dict[str, Any]:
    parsed = urlparse(uri)
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme != "papertrail" or parsed.netloc not in {"documents", "evidence"}:
        raise ValueError("unknown resource URI")
    if parsed.netloc == "evidence" and len(parts) == 2 and parts[1].isdigit():
        value = get_evidence(database, parts[0], int(parts[1]), principal)
    elif parsed.netloc == "documents" and len(parts) == 1 and re.fullmatch(r"[a-fA-F0-9]{64}", parts[0]):
        value = document_metadata(database, parts[0].lower(), principal)
    else:
        raise ValueError("malformed resource URI")
    return {"contents": [{"uri": uri, "mimeType": "application/json" if "title" in value else "text/plain",
                           "text": json.dumps(value, ensure_ascii=False)}]}


def _call(database: Path, name: str, arguments: dict[str, Any],
          principal: Principal = LOCAL_PRINCIPAL) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    if name == "search_papers":
        if set(arguments) - {"query", "limit"}:
            raise ValueError("unknown search_papers argument")
        query = arguments.get("query")
        limit = arguments.get("limit", 5)
        if not isinstance(query, str) or not query.strip() or not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("query and limit do not match tool schema")
        hits = search_papers(database, query, principal, limit=limit)
        safe = [{"title": row["title"], "sha256": row["sha256"], "page": row["pdf_page"],
                 "section": row["section"], "score": row["rank_score"], "chunk_id": row["chunk_id"]}
                for row in hits]
        return {"content": [{"type": "text", "text": json.dumps(safe, ensure_ascii=False)}],
                "structuredContent": {"results": safe}}
    if name == "get_evidence":
        if set(arguments) != {"sha256", "page"}:
            raise ValueError("get_evidence requires sha256 and page only")
        value = get_evidence(database, arguments.get("sha256", ""), arguments.get("page", 0), principal)
        return {"content": [{"type": "text", "text": value["text"]}], "structuredContent": value}
    raise ValueError("unknown tool")


def handle(database: Path, message: dict[str, Any],
           principal: Principal = LOCAL_PRINCIPAL) -> dict[str, Any] | None:
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
                result = _call(database, params.get("name", ""), params.get("arguments", {}), principal)
            except (ValueError, OSError, sqlite3.Error) as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        elif method == "resources/list":
            result = {"resources": _resource_list(database, principal)}
        elif method == "resources/read":
            result = _resource_read(database, params.get("uri", ""), principal)
        else:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"}}
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (ValueError, OSError, sqlite3.Error) as exc:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32602, "message": str(exc)}}


def main(database_path: Path | None = None, principal: Principal = LOCAL_PRINCIPAL) -> None:
    try:
        database = database_path.resolve() if database_path else _database()
        if not database.is_file():
            raise ValueError("indexed database does not exist")
        schema_conn = open_database(database)
        schema_conn.close()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle(database, request, principal)
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
