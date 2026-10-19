"""Evidence-constrained extractive QA and persistent conversations."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz

from .audit import _hash
from .gold import _normalize_excerpt
from .retrieval import retrieve
from .s1_index import open_database

QUESTION_STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "does", "for", "from",
                      "how", "in", "is", "it", "of", "on", "or", "the", "their", "this",
                      "to", "what", "when", "which", "with", "why", "data", "paper", "study",
                      "method", "model", "approach", "result", "的", "了", "吗", "如何", "什么"}


def _ensure_qa_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS qa_conversations (
        conversation_id TEXT PRIMARY KEY, title TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS qa_turns (
        turn_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL
            REFERENCES qa_conversations(conversation_id) ON DELETE CASCADE,
        question TEXT NOT NULL, answer TEXT NOT NULL, status TEXT NOT NULL,
        retrieval_mode TEXT NOT NULL, context_query TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS qa_claims (
        claim_id TEXT PRIMARY KEY, turn_id TEXT NOT NULL
            REFERENCES qa_turns(turn_id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL, claim_text TEXT NOT NULL,
        evidence_json TEXT NOT NULL, UNIQUE(turn_id, ordinal)
    );
    """)


def _validate_quote(path: str, sha256: str, page_number: int, quote: str,
                    page_cache: dict[tuple[str, int, str], str]) -> bool:
    key = (path, page_number, sha256)
    if key not in page_cache:
        source = Path(path)
        if not source.is_file() or _hash(source) != sha256:
            return False
        with fitz.open(source) as doc:
            if page_number < 1 or page_number > doc.page_count:
                return False
            page_cache[key] = _normalize_excerpt(doc[page_number - 1].get_text("text"))
    return _normalize_excerpt(quote) in page_cache[key]


def _sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    return [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text)
            if 35 <= len(part.strip()) <= 500 and re.search(r"[.!?。！？]$", part.strip())]


def ask(database: Path, question: str, conversation_id: str | None = None,
        limit: int = 5, mode: str = "bm25") -> dict[str, Any]:
    question = question.strip()
    if not question:
        raise ValueError("问题不能为空")
    now = datetime.now(timezone.utc).isoformat()
    conversation_id = conversation_id or str(uuid.uuid4())
    conn = open_database(database)
    try:
        _ensure_qa_schema(conn)
        previous = conn.execute(
            "SELECT question FROM qa_turns WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1",
            (conversation_id,)).fetchone()
        if previous is None and conn.execute(
                "SELECT 1 FROM qa_conversations WHERE conversation_id=?", (conversation_id,)).fetchone():
            raise ValueError("该对话尚无历史问题")
        context_query = None
        retrieval_query = question
        if previous and len(re.findall(r"[\w]+", question)) <= 3:
            context_query = previous["question"]
            retrieval_query = context_query + " " + question
        result_rows = retrieve(database, retrieval_query, max(limit * 4, 12),
                               source_type="original_pdf", mode=mode)
        version_meta: dict[str, str] = {}
        for row in result_rows:
            if row.get("text_origin", "native_text") != "native_text":
                continue
            if row["pdf_page"] is None or not row.get("path"):
                continue
            meta = conn.execute("SELECT parser_version FROM paper_versions WHERE version_id=?",
                                (row["version_id"],)).fetchone()
            if meta:
                version_meta[row["version_id"]] = meta["parser_version"]
        conn.commit()
    finally:
        conn.close()

    page_cache: dict[tuple[str, int, str], str] = {}
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    query_terms = {term for term in re.findall(r"[\w]+", retrieval_query.casefold())
                   if term not in QUESTION_STOPWORDS and len(term) > 1}
    minimum_overlap = 2 if len(query_terms) >= 3 else 1
    for result_rank, row in enumerate(result_rows, 1):
        if row.get("text_origin", "native_text") != "native_text" or row["pdf_page"] is None:
            continue
        sentences = _sentences(row["text"])
        for sentence in sentences:
            overlap = len(query_terms.intersection(re.findall(r"[\w]+", sentence.casefold())))
            if not query_terms or overlap < minimum_overlap:
                continue
            title_overlap = len(query_terms.intersection(re.findall(r"[\w]+", row["title"].casefold())))
            candidates.append((overlap + 2 * title_overlap, result_rank, row, sentence))
    candidates.sort(key=lambda item: (-item[0], item[1], -len(item[3])))
    paper_counts: dict[str, int] = {}
    for _, _, row, quote in candidates:
        key = (row["sha256"], row["pdf_page"], quote)
        if key in seen or paper_counts.get(row["paper_id"], 0) >= 2:
            continue
        if not _validate_quote(row["path"], row["sha256"], row["pdf_page"], quote, page_cache):
            continue
        seen.add(key)
        paper_counts[row["paper_id"]] = paper_counts.get(row["paper_id"], 0) + 1
        evidence.append({
            "paper_id": row["paper_id"], "version_id": row["version_id"],
            "sha256": row["sha256"], "pdf_page": row["pdf_page"],
            "chunk_id": row["chunk_id"], "quote": quote,
            "parser_version": version_meta.get(row["version_id"]),
            "title": row["title"], "relevance_score": row["rank_score"],
            "path": row["path"], "text_origin": "native_text",
        })
        if len(evidence) >= limit:
            break
    if evidence:
        status = "verified_excerpts"
        answer = "在当前原文中找到以下逐条核验过的摘录。系统未自动综合其含义；请结合上下文阅读。"
        claims = [{"text": item["quote"], "kind": "verbatim_excerpt", "evidence": item}
                  for item in evidence]
    else:
        status = "abstained"
        answer = "当前检索范围内没有找到可通过原 PDF 哈希、页码和原文校验的证据，因此暂不作答。"
        claims = []

    conn = open_database(database)
    try:
        _ensure_qa_schema(conn)
        exists = conn.execute("SELECT 1 FROM qa_conversations WHERE conversation_id=?",
                              (conversation_id,)).fetchone()
        if not exists:
            conn.execute("INSERT INTO qa_conversations VALUES(?,?,?,?)",
                         (conversation_id, question[:120], now, now))
        else:
            conn.execute("UPDATE qa_conversations SET updated_at=? WHERE conversation_id=?",
                         (now, conversation_id))
        turn_id = str(uuid.uuid4())
        conn.execute("INSERT INTO qa_turns VALUES(?,?,?,?,?,?,?,?)",
                     (turn_id, conversation_id, question, answer, status, mode, context_query, now))
        for ordinal, claim in enumerate(claims, 1):
            conn.execute("INSERT INTO qa_claims VALUES(?,?,?,?,?)",
                         (str(uuid.uuid4()), turn_id, ordinal, claim["text"],
                          json.dumps(claim["evidence"], ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()
    return {"conversation_id": conversation_id, "turn_id": turn_id, "question": question,
            "answer": answer, "status": status, "retrieval_mode": mode,
            "context_query": context_query, "claims": claims, "created_at": now}


def conversation_history(database: Path, conversation_id: str) -> list[dict[str, Any]]:
    conn = open_database(database)
    try:
        _ensure_qa_schema(conn)
        turns = conn.execute("SELECT * FROM qa_turns WHERE conversation_id=? ORDER BY created_at",
                             (conversation_id,)).fetchall()
        result = []
        for turn in turns:
            claims = conn.execute("SELECT ordinal,claim_text,evidence_json FROM qa_claims WHERE turn_id=? ORDER BY ordinal",
                                  (turn["turn_id"],)).fetchall()
            result.append({**dict(turn), "claims": [{"ordinal": row["ordinal"],
                            "text": row["claim_text"], "evidence": json.loads(row["evidence_json"])}
                           for row in claims]})
        return result
    finally:
        conn.close()
