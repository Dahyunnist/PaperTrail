"""Shared principal and collection authorization for evidence reads."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .s1_index import open_database, search as bm25_search


@dataclass(frozen=True)
class Principal:
    user_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("principal user_id must be non-empty")


LOCAL_PRINCIPAL = Principal("local-dev")


def create_collection(database: Path, collection_id: str, owner_id: str) -> None:
    if not collection_id.strip() or not owner_id.strip():
        raise ValueError("collection_id and owner_id must be non-empty")
    conn = open_database(database)
    try:
        conn.execute("INSERT INTO collections(collection_id,owner_id) VALUES(?,?)",
                     (collection_id, owner_id))
        conn.commit()
    finally:
        conn.close()


def assign_version_to_collection(database: Path, version_id: str, collection_id: str) -> None:
    conn = open_database(database)
    try:
        cursor = conn.execute("UPDATE paper_versions SET collection_id=? WHERE version_id=?",
                              (collection_id, version_id))
        if cursor.rowcount != 1:
            raise ValueError("paper version not found")
        conn.commit()
    finally:
        conn.close()


def search_papers(database: Path, query: str, principal: Principal,
                  limit: int = 5) -> list[dict[str, Any]]:
    """Filter by collection owner inside SQL before ranked results are returned."""
    return bm25_search(database, query, limit=limit, source_type="original_pdf",
                       readonly=True, principal_id=principal.user_id)


def authorized_version_ids(database: Path, principal_id: str) -> set[str]:
    conn = open_database(database, readonly=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        return {row[0] for row in conn.execute(
            "SELECT v.version_id FROM paper_versions v JOIN collections col "
            "ON col.collection_id=v.collection_id WHERE col.owner_id=?", (principal_id,))}
    finally:
        conn.close()


def _authorized_document(database: Path, sha256: str, principal: Principal
                         ) -> tuple[dict[str, Any], Path] | None:
    conn = open_database(database, readonly=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        row = conn.execute(
            "SELECT v.version_id,v.sha256,v.parse_status,v.page_count,p.title_candidate "
            "FROM paper_versions v JOIN papers p ON p.paper_id=v.paper_id "
            "JOIN collections col ON col.collection_id=v.collection_id "
            "WHERE v.sha256=? AND v.source_type='original_pdf' AND col.owner_id=?",
            (sha256, principal.user_id),
        ).fetchone()
        if not row:
            return None
        location = conn.execute(
            "SELECT absolute_path FROM source_locations WHERE version_id=? LIMIT 1",
            (row["version_id"],),
        ).fetchone()
        if not location:
            return None
        return dict(row), Path(location["absolute_path"])
    finally:
        conn.close()


def read_evidence(database: Path, sha256: str, page_number: int,
                  principal: Principal) -> dict[str, Any]:
    if (not isinstance(sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", sha256)
            or not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1):
        raise ValueError("invalid SHA-256 or page")
    match = _authorized_document(database, sha256.lower(), principal)
    if not match:
        raise ValueError("original paper not found")
    metadata, path = match
    if not path.is_file():
        raise ValueError("source file changed or is unavailable")
    with path.open("rb") as stream:
        actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual_hash != sha256.lower():
        raise ValueError("source file changed or is unavailable")
    import pymupdf
    with pymupdf.open(path) as doc:
        if page_number > doc.page_count:
            raise ValueError("page is outside source document")
        text = doc[page_number - 1].get_text("text")
    return {"sha256": sha256.lower(), "page": page_number, "title": metadata["title_candidate"],
            "text": text, "text_origin": "native_pdf_page"}


def document_metadata(database: Path, sha256: str, principal: Principal) -> dict[str, Any]:
    match = _authorized_document(database, sha256, principal)
    if not match:
        raise ValueError("original paper not found")
    metadata, _ = match
    return {"sha256": metadata["sha256"], "title": metadata["title_candidate"],
            "page_count": metadata["page_count"], "parse_status": metadata["parse_status"]}
