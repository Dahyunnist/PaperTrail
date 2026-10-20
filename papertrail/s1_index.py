"""S1 text parsing and local SQLite FTS5 index."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import statistics
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from .audit import _candidate_title, _hash, normalize_title

PARSER_VERSION = "papertrail-s1-3"
MAX_CHUNK_CHARS = 1800
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
WORD_RE = re.compile(r"[\w]+", re.UNICODE)
HEADING_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+|[A-Z]\.\s+).{2,160}$")
SENTENCE_END_RE = re.compile(r"[.!?。！？；;:]\s*$")


@dataclass
class ParsedBlock:
    section_title: str
    page_number: int | None
    block_index: int
    text: str
    text_origin: str = "native_text"


@dataclass
class ParsedDocument:
    title: str
    doi_candidates: list[str]
    page_count: int | None
    parseable_pages: int | None
    low_text_pages: list[int]
    parse_status: str
    source_type: str
    blocks: list[ParsedBlock]
    ocr_pages: list[int]
    ocr_errors: list[str]


def _title_from_pdf(path: Path, metadata: dict[str, Any], first_page: str) -> str:
    return _candidate_title(path, metadata.get("title") or "", first_page)


def _looks_like_heading(text: str, sizes: list[float], bold_flags: list[bool], body_size: float) -> bool:
    clean = " ".join(text.split())
    if not clean or len(clean) > 200 or len(WORD_RE.findall(clean)) > 24:
        return False
    if re.search(r"@|https?://", clean) or SENTENCE_END_RE.search(clean):
        return False
    larger = bool(sizes) and max(sizes) >= body_size * 1.15
    bold = bool(bold_flags) and sum(bold_flags) / len(bold_flags) >= 0.6
    numbered = bool(HEADING_RE.match(clean))
    short_unpunctuated = (len(clean.splitlines()) <= 2 and len(clean) <= 100 and
                          len(clean.split()) <= 12 and not re.search(r"[=<>]{1,}|\|", clean))
    return numbered or larger or bold or short_unpunctuated


def parse_pdf(path: Path, source_type: str, ocr_fallback: bool = False) -> ParsedDocument:
    import fitz

    with fitz.open(path) as doc:
        page_count = doc.page_count
        page_texts = [page.get_text("text") for page in doc]
        first_page = page_texts[0] if page_texts else ""
        metadata = doc.metadata or {}
        title = _title_from_pdf(path, metadata, first_page)
        doi_candidates = sorted({m.rstrip(".,;)").casefold() for m in DOI_RE.findall("\n".join(page_texts[:2]))})
        ocr_pages: list[int] = []
        ocr_errors: list[str] = []
        ocr_text_by_page: dict[int, Any] = {}
        if ocr_fallback:
            for page_no, page in enumerate(doc, 1):
                if len(WORD_RE.findall(page_texts[page_no - 1])) >= 12:
                    continue
                try:
                    textpage = page.get_textpage_ocr(language="eng", dpi=200, full=True)
                    recognized = page.get_text("text", textpage=textpage)
                    if len(WORD_RE.findall(recognized)) >= 12:
                        page_texts[page_no - 1] = recognized
                        ocr_pages.append(page_no)
                        ocr_text_by_page[page_no] = textpage
                except Exception as exc:
                    ocr_errors.append(f"PDF 第 {page_no} 页：{type(exc).__name__}: {exc}")
        blocks: list[ParsedBlock] = []
        current_section = "Document"
        block_index = 0
        for page_no, page in enumerate(doc, 1):
            origin = "ocr_derived" if page_no in ocr_text_by_page else "native_text"
            page_dict = page.get_text("dict", textpage=ocr_text_by_page.get(page_no), sort=True)
            spans = [span for block in page_dict.get("blocks", []) if block.get("type") == 0
                     for line in block.get("lines", []) for span in line.get("spans", []) if span.get("text", "").strip()]
            font_sizes = [float(span.get("size", 10.0)) for span in spans]
            body_size = statistics.median(font_sizes) if font_sizes else 10.0
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                lines: list[str] = []
                sizes: list[float] = []
                bold_flags: list[bool] = []
                for line in block.get("lines", []):
                    line_spans = line.get("spans", [])
                    line_text = "".join(span.get("text", "") for span in line_spans).strip()
                    if line_text:
                        lines.append(line_text)
                        sizes.extend(float(span.get("size", 10.0)) for span in line_spans if span.get("text", "").strip())
                        bold_flags.extend(bool(int(span.get("flags", 0)) & 16) for span in line_spans if span.get("text", "").strip())
                text = "\n".join(lines).strip()
                if not text:
                    continue
                if _looks_like_heading(text, sizes, bold_flags, body_size):
                    current_section = " ".join(text.split())[:200]
                    # Keep the heading searchable as a short child block.
                blocks.append(ParsedBlock(current_section, page_no, block_index, text, origin))
                block_index += 1
        # Repeated running heads/footers pollute lexical ranking (especially the repeated
        # paper title). Keep the title in metadata, but omit boilerplate blocks from FTS.
        repeated_pages: dict[str, set[int]] = {}
        for block in blocks:
            key = normalize_title(block.text)
            if block.page_number is not None and len(key) >= 12:
                repeated_pages.setdefault(key, set()).add(block.page_number)
        repetition_threshold = max(2, math.ceil(page_count * 0.25))
        running_matter = {key for key, pages in repeated_pages.items() if len(pages) >= repetition_threshold}
        blocks = [block for block in blocks if normalize_title(block.text) not in running_matter]
        parseable_pages = [i for i, text in enumerate(page_texts, 1) if len(WORD_RE.findall(text)) >= 12]
        low_text_pages = [i for i, text in enumerate(page_texts, 1) if len(WORD_RE.findall(text)) < 12]
    if page_count == 0:
        status = "empty_pdf"
    elif not parseable_pages:
        status = "low_text"
    elif low_text_pages:
        status = "partial_text"
    else:
        status = "text"
    if ocr_pages:
        status = "ocr_text" if not low_text_pages else "partial_ocr_text"
    return ParsedDocument(title, doi_candidates, page_count, len(parseable_pages), low_text_pages,
                          status, source_type, blocks, ocr_pages, ocr_errors)


def _split_long(text: str, limit: int = MAX_CHUNK_CHARS) -> list[tuple[str, int, int]]:
    if len(text) <= limit:
        return [(text.strip(), 0, len(text))] if text.strip() else []
    out: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + limit // 2, end), text.rfind(" ", start + limit // 2, end))
            if boundary > start:
                end = boundary
        raw = text[start:end]
        left_trim = len(raw) - len(raw.lstrip())
        right_trimmed = raw.rstrip()
        segment = right_trimmed.lstrip()
        actual_start = start + left_trim
        actual_end = start + len(right_trimmed)
        if segment:
            out.append((segment, actual_start, actual_end))
        start = max(end, start + 1)
    return out


def parse_markdown(path: Path, source_type: str) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    sections: list[tuple[str, str]] = []
    current_section = "Document"
    paragraph_lines: list[str] = []

    def flush() -> None:
        nonlocal paragraph_lines
        value = "\n".join(paragraph_lines).strip()
        if value:
            sections.append((current_section, value))
        paragraph_lines = []

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            heading = line.lstrip("# ").strip()
            if heading and title == path.stem:
                title = heading
            current_section = heading or current_section
        elif not line.strip():
            flush()
        else:
            paragraph_lines.append(line)
    flush()
    blocks = [ParsedBlock(section, None, i, value) for i, (section, value) in enumerate(sections)]
    doi_candidates = sorted({m.rstrip(".,;)").casefold() for m in DOI_RE.findall(text[:250_000])})
    return ParsedDocument(title, doi_candidates, None, None, [], "text", source_type, blocks, [], [])


def _identity(title: str, doi_candidates: list[str]) -> tuple[str, str, str]:
    # DOI is a stronger provisional key only when the front matter yielded exactly one.
    if len(doi_candidates) == 1:
        basis = "doi"
        value = doi_candidates[0]
    else:
        basis = "title_candidate"
        value = normalize_title(title) or title.casefold()
    paper_id = "p_" + hashlib.sha256(f"{basis}:{value}".encode("utf-8")).hexdigest()[:24]
    return paper_id, basis, value


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY,
            title_candidate TEXT NOT NULL,
            identity_basis TEXT NOT NULL,
            identity_value TEXT NOT NULL,
            identity_status TEXT NOT NULL DEFAULT 'provisional'
        );
        CREATE TABLE IF NOT EXISTS paper_versions (
            version_id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL REFERENCES papers(paper_id),
            sha256 TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            page_count INTEGER,
            parseable_pages INTEGER,
            low_text_pages_json TEXT NOT NULL,
            parse_status TEXT NOT NULL,
            doi_candidates_json TEXT NOT NULL,
            ocr_pages_json TEXT NOT NULL DEFAULT '[]',
            ocr_errors_json TEXT NOT NULL DEFAULT '[]',
            parser_version TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_locations (
            location_id INTEGER PRIMARY KEY,
            version_id TEXT NOT NULL REFERENCES paper_versions(version_id) ON DELETE CASCADE,
            root_id TEXT NOT NULL,
            absolute_path TEXT NOT NULL,
            UNIQUE(version_id, absolute_path)
        );
        CREATE TABLE IF NOT EXISTS version_dois (
            version_id TEXT NOT NULL REFERENCES paper_versions(version_id) ON DELETE CASCADE,
            doi TEXT NOT NULL,
            PRIMARY KEY(version_id, doi)
        );
        CREATE TABLE IF NOT EXISTS sections (
            section_id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL REFERENCES paper_versions(version_id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            ordinal INTEGER NOT NULL,
            parent_text TEXT NOT NULL,
            UNIQUE(version_id, ordinal)
        );
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL REFERENCES paper_versions(version_id) ON DELETE CASCADE,
            section_id TEXT NOT NULL REFERENCES sections(section_id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            section_title TEXT NOT NULL,
            page_number INTEGER,
            block_index INTEGER NOT NULL,
            piece_index INTEGER NOT NULL,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            parent_chunk_id TEXT NOT NULL,
            text_origin TEXT NOT NULL DEFAULT 'native_text',
            body TEXT NOT NULL,
            UNIQUE(version_id, page_number, block_index, piece_index)
        );
        CREATE INDEX IF NOT EXISTS idx_versions_paper ON paper_versions(paper_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_version_page ON chunks(version_id, page_number);
        CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO app_metadata(key,value) VALUES('index_revision','0');
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED, title, section_title, body,
            tokenize='unicode61 remove_diacritics 2'
        );
        PRAGMA user_version=1;
        """
    )
    version_columns = {row[1] for row in conn.execute("PRAGMA table_info(paper_versions)")}
    if "ocr_pages_json" not in version_columns:
        conn.execute("ALTER TABLE paper_versions ADD COLUMN ocr_pages_json TEXT NOT NULL DEFAULT '[]'")
    if "ocr_errors_json" not in version_columns:
        conn.execute("ALTER TABLE paper_versions ADD COLUMN ocr_errors_json TEXT NOT NULL DEFAULT '[]'")
    chunk_columns = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    if "text_origin" not in chunk_columns:
        conn.execute("ALTER TABLE chunks ADD COLUMN text_origin TEXT NOT NULL DEFAULT 'native_text'")


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _selection_rows(selection_path: Path, source_config_path: Path) -> list[dict[str, Any]]:
    config = yaml.safe_load(source_config_path.read_text(encoding="utf-8"))
    roots = {root["id"]: Path(root["path"]) for root in config.get("roots", [])}
    selected: list[dict[str, Any]] = []
    for line_no, line in enumerate(selection_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("root_id") not in roots:
            raise ValueError(f"selection 第 {line_no} 行来源目录不存在：{item.get('root_id')}")
        base = roots[item["root_id"]].resolve()
        if item.get("relative_path"):
            candidate = (base / item["relative_path"]).resolve()
            if not candidate.is_relative_to(base):
                raise ValueError(f"selection 第 {line_no} 行路径越出授权源目录")
            candidates = [candidate] if candidate.is_file() and candidate.name == item["file_name"] else []
        else:
            candidates = [p for p in base.rglob(item["file_name"]) if p.is_file()]
        path = next((p for p in candidates if _hash(p) == item["sha256"]), None)
        if path is None:
            raise ValueError(f"selection 第 {line_no} 行没有匹配哈希的源文件：{item['file_name']}")
        item["path"] = path.resolve()
        selected.append(item)
    return selected


def _remove_version_content(conn: sqlite3.Connection, version_id: str) -> None:
    ids = [row[0] for row in conn.execute("SELECT chunk_id FROM chunks WHERE version_id=?", (version_id,))]
    conn.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", ((chunk_id,) for chunk_id in ids))
    conn.execute("DELETE FROM paper_versions WHERE version_id=?", (version_id,))


def _insert_document(conn: sqlite3.Connection, item: dict[str, Any], parsed: ParsedDocument) -> dict[str, int]:
    path: Path = item["path"]
    sha256 = item["sha256"]
    version_id = "v_" + sha256
    paper_id, identity_basis, identity_value = _identity(parsed.title, parsed.doi_candidates)
    conn.execute(
        "INSERT INTO papers(paper_id,title_candidate,identity_basis,identity_value,identity_status) VALUES(?,?,?,?,?) "
        "ON CONFLICT(paper_id) DO UPDATE SET title_candidate=excluded.title_candidate",
        (paper_id, parsed.title, identity_basis, identity_value, "provisional"),
    )
    existing = conn.execute("SELECT parser_version FROM paper_versions WHERE sha256=?", (sha256,)).fetchone()
    if existing and existing["parser_version"] == PARSER_VERSION:
        conn.execute("INSERT OR IGNORE INTO source_locations(version_id,root_id,absolute_path) VALUES(?,?,?)",
                     (version_id, item["root_id"], str(path)))
        return {"added": 0, "duplicate": 1, "sections": 0, "chunks": 0}
    if existing:
        _remove_version_content(conn, version_id)
    stat = path.stat()
    conn.execute(
        "INSERT OR REPLACE INTO paper_versions(version_id,paper_id,sha256,source_type,file_name,file_size,page_count,parseable_pages,low_text_pages_json,parse_status,doi_candidates_json,ocr_pages_json,ocr_errors_json,parser_version,indexed_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (version_id, paper_id, sha256, item["source_type"], path.name, stat.st_size,
         parsed.page_count, parsed.parseable_pages, json.dumps(parsed.low_text_pages), parsed.parse_status,
         json.dumps(parsed.doi_candidates), json.dumps(parsed.ocr_pages), json.dumps(parsed.ocr_errors),
         PARSER_VERSION, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("INSERT OR IGNORE INTO source_locations(version_id,root_id,absolute_path) VALUES(?,?,?)",
                 (version_id, item["root_id"], str(path)))
    conn.executemany("INSERT OR IGNORE INTO version_dois(version_id,doi) VALUES(?,?)",
                     ((version_id, doi) for doi in parsed.doi_candidates))
    section_groups: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for block in parsed.blocks:
        group = by_key.get(block.section_title)
        if group is None:
            group = {"title": block.section_title, "pages": [], "texts": [], "blocks": []}
            by_key[block.section_title] = group
            section_groups.append(group)
        if block.page_number is not None:
            group["pages"].append(block.page_number)
        group["texts"].append(block.text)
        group["blocks"].append(block)
    section_id_by_title: dict[str, str] = {}
    for ordinal, section in enumerate(section_groups):
        section_id = hashlib.sha256(f"{version_id}|{PARSER_VERSION}|section|{ordinal}|{section['title']}".encode("utf-8")).hexdigest()
        section_id_by_title[section["title"]] = section_id
        pages = section["pages"]
        conn.execute("INSERT INTO sections(section_id,version_id,title,page_start,page_end,ordinal,parent_text) VALUES(?,?,?,?,?,?,?)",
                     (section_id, version_id, section["title"], min(pages) if pages else None,
                      max(pages) if pages else None, ordinal, "\n\n".join(section["texts"])))
    child_count = 0
    for block in parsed.blocks:
        section_id = section_id_by_title[block.section_title]
        pieces = _split_long(block.text)
        parent_id = hashlib.sha256(f"{version_id}|{PARSER_VERSION}|parent|{block.page_number}|{block.block_index}".encode("utf-8")).hexdigest()
        for piece_index, (body, start, end) in enumerate(pieces):
            chunk_id = hashlib.sha256(f"{version_id}|{PARSER_VERSION}|chunk|{block.page_number}|{block.block_index}|{piece_index}".encode("utf-8")).hexdigest()
            conn.execute(
                "INSERT INTO chunks(chunk_id,version_id,section_id,source_type,title,section_title,page_number,block_index,piece_index,char_start,char_end,parent_chunk_id,text_origin,body) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (chunk_id, version_id, section_id, item["source_type"], parsed.title, block.section_title,
                 block.page_number, block.block_index, piece_index, start, end, parent_id, block.text_origin, body),
            )
            conn.execute("INSERT INTO chunks_fts(chunk_id,title,section_title,body) VALUES(?,?,?,?)",
                         (chunk_id, parsed.title, block.section_title, body))
            child_count += 1
    return {"added": 1, "duplicate": 0, "sections": len(section_groups), "chunks": child_count}


def index_selection(database: Path, sources: Path, selection: Path, ocr_fallback: bool = False) -> dict[str, Any]:
    selected = _selection_rows(selection, sources)
    conn = open_database(database)
    totals = {"selected": len(selected), "added": 0, "duplicates": 0, "sections": 0, "chunks": 0, "low_text_documents": 0}
    issues: list[dict[str, str]] = []
    seen_sha: set[str] = set()
    try:
        for item in selected:
            if item["sha256"] in seen_sha:
                existing = conn.execute("SELECT version_id FROM paper_versions WHERE sha256=?", (item["sha256"],)).fetchone()
                if existing:
                    conn.execute("INSERT OR IGNORE INTO source_locations(version_id,root_id,absolute_path) VALUES(?,?,?)",
                                 (existing["version_id"], item["root_id"], str(item["path"])))
                totals["duplicates"] += 1
                continue
            seen_sha.add(item["sha256"])
            try:
                parsed = parse_pdf(item["path"], item["source_type"], ocr_fallback) if item["kind"] == "pdf" else parse_markdown(item["path"], item["source_type"])
                with conn:
                    counts = _insert_document(conn, item, parsed)
                totals["added"] += counts["added"]
                totals["duplicates"] += counts["duplicate"]
                totals["sections"] += counts["sections"]
                totals["chunks"] += counts["chunks"]
                if parsed.low_text_pages:
                    totals["low_text_documents"] += 1
                    issues.append({"file_name": item["file_name"], "issue": "low_text_pages", "pages": ",".join(map(str, parsed.low_text_pages))})
                if parsed.ocr_errors:
                    issues.append({"file_name": item["file_name"], "issue": "ocr_errors", "details": " | ".join(parsed.ocr_errors)})
                if parsed.ocr_pages:
                    issues.append({"file_name": item["file_name"], "issue": "ocr_derived_pages", "pages": ",".join(map(str, parsed.ocr_pages))})
            except Exception as exc:
                issues.append({"file_name": item["file_name"], "issue": f"{type(exc).__name__}: {exc}"})
        conn.commit()
        if totals["added"]:
            conn.execute("UPDATE app_metadata SET value=CAST(value AS INTEGER)+1 WHERE key='index_revision'")
            conn.commit()
    finally:
        conn.close()
    totals["issues"] = issues
    return totals


def _query_terms(query: str) -> list[str]:
    terms = WORD_RE.findall(unicodedata.normalize("NFKC", query).casefold())
    seen: set[str] = set()
    return [term for term in terms if term not in seen and not seen.add(term)]


def search(database: Path, query: str, limit: int = 5, source_type: str | None = None) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    if not terms:
        return []
    doi_match = DOI_RE.search(query)
    if doi_match:
        exact_doi = doi_match.group(0).rstrip(".,;)").casefold()
        conn = open_database(database)
        try:
            sql = (
                "SELECT c.chunk_id,c.version_id,c.source_type,c.title,c.section_title,c.page_number,c.text_origin,c.body,"
                "p.paper_id,v.sha256,v.parse_status,l.absolute_path FROM version_dois d "
                "JOIN paper_versions v ON v.version_id=d.version_id JOIN papers p ON p.paper_id=v.paper_id "
                "JOIN chunks c ON c.version_id=v.version_id JOIN source_locations l ON l.version_id=v.version_id "
                "WHERE d.doi=?"
            )
            params: list[Any] = [exact_doi]
            if source_type:
                sql += " AND c.source_type=?"
                params.append(source_type)
            sql += " ORDER BY COALESCE(c.page_number,0),c.block_index,c.piece_index LIMIT ?"
            params.append(max(1, limit) * 4)
            rows = conn.execute(sql, params).fetchall()
            return [{
                "paper_id": row["paper_id"], "version_id": row["version_id"], "sha256": row["sha256"],
                "source_type": row["source_type"], "title": row["title"], "section": row["section_title"],
                "pdf_page": row["page_number"], "path": row["absolute_path"], "parse_status": row["parse_status"], "text_origin": row["text_origin"],
                "rank_score": 1.0, "text": row["body"], "chunk_id": row["chunk_id"],
            } for row in rows[:limit]]
        finally:
            conn.close()
    quoted_terms = ['"' + term.replace('"', '""') + '"' for term in terms]
    and_query = "body : (" + " AND ".join(quoted_terms) + ")"
    or_query = "body : (" + " OR ".join(quoted_terms) + ")"
    conn = open_database(database)
    try:
        sql = (
            "SELECT c.chunk_id,c.version_id,c.source_type,c.title,c.section_title,c.page_number,c.text_origin,c.body,"
            "p.paper_id,p.title_candidate,v.sha256,v.parse_status,l.absolute_path,"
            "bm25(chunks_fts,0,4.0,2.0,1.0) AS bm25_score "
            "FROM chunks_fts JOIN chunks c ON c.chunk_id=chunks_fts.chunk_id "
            "JOIN paper_versions v ON v.version_id=c.version_id JOIN papers p ON p.paper_id=v.paper_id "
            "JOIN source_locations l ON l.version_id=v.version_id "
            "WHERE chunks_fts MATCH ?"
        )
        params: list[Any] = [and_query]
        filtered_sql = sql
        if source_type:
            filtered_sql += " AND c.source_type=?"
            params.append(source_type)
        filtered_sql += " ORDER BY bm25_score LIMIT ?"
        params.append(max(1, limit) * 4)
        rows = conn.execute(filtered_sql, params).fetchall()
        if not rows and len(terms) > 1:
            fallback_params: list[Any] = [or_query]
            if source_type:
                fallback_params.append(source_type)
            fallback_params.append(max(1, limit) * 4)
            rows = conn.execute(filtered_sql, fallback_params).fetchall()
        # A query containing only a document title should still find its first pages.
        if not rows:
            title_terms = [f"%{term}%" for term in terms]
            title_filter = " AND ".join("lower(p.title_candidate) LIKE ?" for _ in title_terms)
            title_sql = (
                "SELECT c.chunk_id,c.version_id,c.source_type,c.title,c.section_title,c.page_number,c.text_origin,c.body,"
                "p.paper_id,p.title_candidate,v.sha256,v.parse_status,l.absolute_path "
                "FROM paper_versions v JOIN papers p ON p.paper_id=v.paper_id "
                "JOIN chunks c ON c.version_id=v.version_id JOIN source_locations l ON l.version_id=v.version_id "
                f"WHERE {title_filter}"
            )
            title_params: list[Any] = title_terms
            if source_type:
                title_sql += " AND c.source_type=?"
                title_params.append(source_type)
            title_sql += " ORDER BY COALESCE(c.page_number,0),c.block_index,c.piece_index LIMIT ?"
            title_params.append(max(1, limit) * 4)
            title_rows = conn.execute(title_sql, title_params).fetchall()
            title_results = [{
                "paper_id": row["paper_id"], "version_id": row["version_id"], "sha256": row["sha256"],
                "source_type": row["source_type"], "title": row["title"], "section": row["section_title"],
                "pdf_page": row["page_number"], "path": row["absolute_path"], "parse_status": row["parse_status"], "text_origin": row["text_origin"],
                "rank_score": 1.0, "text": row["body"], "chunk_id": row["chunk_id"],
            } for row in title_rows]
            return title_results[:limit]
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, int | None, str]] = set()
        for row in rows:
            identity = (row["sha256"], row["page_number"], row["body"])
            if identity in seen:
                continue
            seen.add(identity)
            results.append({
                "paper_id": row["paper_id"], "version_id": row["version_id"], "sha256": row["sha256"],
                "source_type": row["source_type"], "title": row["title"], "section": row["section_title"],
                "pdf_page": row["page_number"], "path": row["absolute_path"], "parse_status": row["parse_status"],
                "text_origin": row["text_origin"], "rank_score": -float(row["bm25_score"]), "text": row["body"], "chunk_id": row["chunk_id"],
            })
            if len(results) >= limit:
                break
        return results
    finally:
        conn.close()


def inspect_document(database: Path, identifier: str) -> dict[str, Any] | None:
    conn = open_database(database)
    try:
        row = conn.execute(
            "SELECT v.*,p.paper_id,p.title_candidate,p.identity_basis,p.identity_status "
            "FROM paper_versions v JOIN papers p ON p.paper_id=v.paper_id "
            "WHERE v.sha256 LIKE ? OR v.version_id LIKE ? OR p.paper_id LIKE ? LIMIT 1",
            (identifier + "%", identifier + "%", identifier + "%"),
        ).fetchone()
        if row is None:
            return None
        locations = [dict(r) for r in conn.execute("SELECT root_id,absolute_path FROM source_locations WHERE version_id=? ORDER BY root_id,absolute_path", (row["version_id"],))]
        sections = [dict(r) for r in conn.execute("SELECT title,page_start,page_end,ordinal FROM sections WHERE version_id=? ORDER BY ordinal", (row["version_id"],))]
        counts = conn.execute("SELECT COUNT(*) AS chunks FROM chunks WHERE version_id=?", (row["version_id"],)).fetchone()
        result = dict(row)
        result["low_text_pages"] = json.loads(result.pop("low_text_pages_json"))
        result["doi_candidates"] = json.loads(result.pop("doi_candidates_json"))
        result["ocr_pages"] = json.loads(result.pop("ocr_pages_json"))
        result["ocr_errors"] = json.loads(result.pop("ocr_errors_json"))
        result["locations"] = locations
        result["sections"] = sections
        result["chunk_count"] = counts["chunks"]
        return result
    finally:
        conn.close()


def database_summary(database: Path) -> dict[str, Any]:
    conn = open_database(database)
    try:
        docs = conn.execute("SELECT COUNT(*) FROM paper_versions").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        notes = conn.execute("SELECT COUNT(*) FROM paper_versions WHERE source_type='reading_note'").fetchone()[0]
        locations = conn.execute("SELECT COUNT(*) FROM source_locations").fetchone()[0]
        return {"documents": docs, "chunks": chunks, "reading_notes": notes, "source_locations": locations}
    finally:
        conn.close()
