"""Cross-paper evidence collection with explicit human stance labels."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .qa import QUESTION_STOPWORDS, _sentences, _validate_quote
from .retrieval import retrieve
from .s1_index import open_database

LABELS = {"unclassified", "supports", "contradicts", "conditions", "context", "unclear"}


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS comparisons (
        comparison_id TEXT PRIMARY KEY, topic TEXT NOT NULL, claim TEXT NOT NULL,
        retrieval_mode TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS comparison_evidence (
        evidence_id TEXT PRIMARY KEY, comparison_id TEXT NOT NULL
            REFERENCES comparisons(comparison_id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL, paper_id TEXT NOT NULL, version_id TEXT NOT NULL,
        sha256 TEXT NOT NULL, title TEXT NOT NULL, pdf_page INTEGER NOT NULL,
        chunk_id TEXT NOT NULL, quote TEXT NOT NULL, parser_version TEXT,
        relevance_score REAL NOT NULL, path TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT 'unclassified'
            CHECK(label IN ('unclassified','supports','contradicts','conditions','context','unclear')),
        rationale TEXT NOT NULL DEFAULT '', labeled_at TEXT,
        UNIQUE(comparison_id,ordinal)
    );
    CREATE TABLE IF NOT EXISTS comparison_gaps (
        gap_id TEXT PRIMARY KEY, comparison_id TEXT NOT NULL
            REFERENCES comparisons(comparison_id) ON DELETE CASCADE,
        note TEXT NOT NULL, basis_evidence_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'user_proposed', created_at TEXT NOT NULL
    );
    """)


def compare_papers(database: Path, topic: str, claim: str, limit_papers: int = 8,
                   mode: str = "bm25") -> dict[str, Any]:
    topic, claim = topic.strip(), claim.strip()
    if not topic or not claim:
        raise ValueError("主题和待比较论断都不能为空")
    relevance_text = f"{topic} {claim}"
    terms = {term for term in re.findall(r"[\w]+", relevance_text.casefold())
             if term not in QUESTION_STOPWORDS and len(term) > 1}
    topic_terms = {term for term in re.findall(r"[\w]+", topic.casefold())
                   if term not in QUESTION_STOPWORDS and len(term) > 1}
    rows_by_chunk: dict[str, dict[str, Any]] = {}
    for token in sorted(topic_terms or terms):
        token_rows = retrieve(database, token, max(limit_papers * 12, 48),
                              source_type="original_pdf", mode=mode)
        for row in token_rows:
            prior = rows_by_chunk.get(row["chunk_id"])
            if prior is None or row["rank_score"] > prior["rank_score"]:
                rows_by_chunk[row["chunk_id"]] = row
    rows = sorted(rows_by_chunk.values(), key=lambda row: row["rank_score"], reverse=True)
    # This stage collects candidates for human review, so one specific shared
    # term is enough; it does not infer that the evidence supports the claim.
    min_overlap = 1
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    for rank, row in enumerate(rows, 1):
        if row.get("text_origin", "native_text") != "native_text" or row["pdf_page"] is None:
            continue
        for sentence in _sentences(row["text"]):
            overlap = len(terms.intersection(re.findall(r"[\w]+", sentence.casefold())))
            if overlap >= min_overlap:
                title_overlap = len(terms.intersection(re.findall(r"[\w]+", row["title"].casefold())))
                candidates.append((overlap + 2 * title_overlap, rank, row, sentence))
    candidates.sort(key=lambda item: (-item[0], item[1], -len(item[3])))
    comparison_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    page_cache: dict[tuple[str, int, str], str] = {}
    papers: set[str] = set()
    counts: dict[str, int] = {}
    chosen: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for max_per_paper in (1, 2):
        for _, _, row, quote in candidates:
            paper_id = row["paper_id"]
            key = (row["sha256"], row["pdf_page"], quote)
            if key in seen or counts.get(paper_id, 0) >= max_per_paper:
                continue
            if paper_id not in papers and len(papers) >= limit_papers:
                continue
            if not _validate_quote(row["path"], row["sha256"], row["pdf_page"], quote, page_cache):
                continue
            seen.add(key)
            papers.add(paper_id)
            counts[paper_id] = counts.get(paper_id, 0) + 1
            chosen.append({"evidence_id": str(uuid.uuid4()), "paper_id": paper_id,
                           "version_id": row["version_id"], "sha256": row["sha256"],
                           "title": row["title"], "pdf_page": row["pdf_page"],
                           "chunk_id": row["chunk_id"], "quote": quote,
                           "parser_version": None, "relevance_score": row["rank_score"],
                           "path": row["path"], "label": "unclassified", "rationale": ""})
    conn = open_database(database)
    try:
        _ensure_schema(conn)
        conn.execute("INSERT INTO comparisons VALUES(?,?,?,?,?)",
                     (comparison_id, topic, claim, mode, now))
        for ordinal, item in enumerate(chosen, 1):
            parser = conn.execute("SELECT parser_version FROM paper_versions WHERE version_id=?",
                                  (item["version_id"],)).fetchone()
            item["parser_version"] = parser["parser_version"] if parser else None
            conn.execute(
                "INSERT INTO comparison_evidence(evidence_id,comparison_id,ordinal,paper_id,version_id,sha256,title,pdf_page,chunk_id,quote,parser_version,relevance_score,path,label,rationale) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item["evidence_id"], comparison_id, ordinal, item["paper_id"], item["version_id"],
                 item["sha256"], item["title"], item["pdf_page"], item["chunk_id"], item["quote"],
                 item["parser_version"], item["relevance_score"], item["path"], item["label"], item["rationale"]))
        conn.commit()
    finally:
        conn.close()
    return {"comparison_id": comparison_id, "topic": topic, "claim": claim,
            "retrieval_mode": mode, "paper_count": len(papers), "evidence": chosen,
            "notice": "证据只按论文并列；立场须由用户标注，系统不自动推断支持或反对。"}


def label_evidence(database: Path, evidence_id: str, label: str,
                   rationale: str = "") -> dict[str, Any]:
    if label not in LABELS - {"unclassified"}:
        raise ValueError(f"label 必须是：{', '.join(sorted(LABELS - {'unclassified'}))}")
    conn = open_database(database)
    try:
        _ensure_schema(conn)
        cursor = conn.execute(
            "UPDATE comparison_evidence SET label=?,rationale=?,labeled_at=? WHERE evidence_id=?",
            (label, rationale.strip(), datetime.now(timezone.utc).isoformat(), evidence_id))
        if cursor.rowcount != 1:
            raise ValueError("找不到该比较证据")
        conn.commit()
        return dict(conn.execute("SELECT * FROM comparison_evidence WHERE evidence_id=?",
                                 (evidence_id,)).fetchone())
    finally:
        conn.close()


def comparison_report(database: Path, comparison_id: str) -> dict[str, Any] | None:
    conn = open_database(database)
    try:
        _ensure_schema(conn)
        comparison = conn.execute("SELECT * FROM comparisons WHERE comparison_id=?",
                                  (comparison_id,)).fetchone()
        if comparison is None:
            return None
        evidence = [dict(row) for row in conn.execute(
            "SELECT * FROM comparison_evidence WHERE comparison_id=? ORDER BY ordinal",
            (comparison_id,))]
        gaps = [dict(row) for row in conn.execute(
            "SELECT * FROM comparison_gaps WHERE comparison_id=? ORDER BY created_at",
            (comparison_id,))]
        for gap in gaps:
            gap["basis_evidence_ids"] = json.loads(gap.pop("basis_evidence_json"))
        return {**dict(comparison), "evidence": evidence, "gap_candidates": gaps,
                "stance_summary": {label: sum(item["label"] == label for item in evidence)
                                   for label in sorted(LABELS)}}
    finally:
        conn.close()


def add_gap_candidate(database: Path, comparison_id: str, note: str,
                      evidence_ids: list[str] | None = None) -> dict[str, Any]:
    note = note.strip()
    if not note:
        raise ValueError("研究空白候选说明不能为空")
    evidence_ids = evidence_ids or []
    conn = open_database(database)
    try:
        _ensure_schema(conn)
        if not conn.execute("SELECT 1 FROM comparisons WHERE comparison_id=?", (comparison_id,)).fetchone():
            raise ValueError("没有找到该比较记录")
        if evidence_ids:
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = conn.execute(
                f"SELECT evidence_id FROM comparison_evidence WHERE comparison_id=? AND evidence_id IN ({placeholders})",
                (comparison_id, *evidence_ids)).fetchall()
            if len(rows) != len(set(evidence_ids)):
                raise ValueError("空白候选引用的证据 ID 不属于该比较记录")
        gap = {"gap_id": str(uuid.uuid4()), "comparison_id": comparison_id,
               "note": note, "basis_evidence_ids": evidence_ids,
               "status": "user_proposed", "created_at": datetime.now(timezone.utc).isoformat()}
        conn.execute("INSERT INTO comparison_gaps VALUES(?,?,?,?,?,?)",
                     (gap["gap_id"], comparison_id, note, json.dumps(evidence_ids),
                      gap["status"], gap["created_at"]))
        conn.commit()
        return gap
    finally:
        conn.close()
