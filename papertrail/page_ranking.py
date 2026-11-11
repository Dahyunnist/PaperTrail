"""Parent-aware page ranking for offline PT2 diagnostics."""
from __future__ import annotations
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .retrieval import bm25_search, hybrid_search, vector_search
from .s1_index import open_database

_PAPER_PAIR = re.compile(
    r"\b(?:(?:both\s+)?the\s+)?(?P<first>[A-Za-z][\w]*(?:-[\w]+)+)\s+and\s+"
    r"(?P<second>[A-Za-z][\w]*(?:-[\w]+)+)\s+papers\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _alias_tokens(alias: str) -> set[str]:
    return {token.casefold() for token in _WORD.findall(alias)}


def _resolve_alias(alias: str, papers: list[dict[str, str]]) -> str | None:
    tokens = _alias_tokens(alias)
    if len(tokens) < 2:
        return None
    matches = [paper["paper_id"] for paper in papers
               if tokens.issubset(_alias_tokens(paper["title"]))]
    distinct = list(dict.fromkeys(matches))
    return distinct[0] if len(distinct) == 1 else None


def resolve_explicit_paper_pair(database: Path, query: str
                                ) -> tuple[list[tuple[str, str]], str] | None:
    """Resolve two hyphenated paper aliases stated in the query, never using gold labels."""
    match = _PAPER_PAIR.search(query)
    if not match:
        return None
    conn = open_database(database, readonly=True)
    try:
        papers = [dict(row) for row in conn.execute(
            "SELECT DISTINCT p.paper_id,p.title_candidate AS title FROM papers p "
            "JOIN paper_versions v ON v.paper_id=p.paper_id ORDER BY p.paper_id")]
    finally:
        conn.close()
    aliases = [match.group("first"), match.group("second")]
    resolved = [_resolve_alias(alias, papers) for alias in aliases]
    if any(not paper_id for paper_id in resolved) or len(set(resolved)) != 2:
        return None
    clean_query = _PAPER_PAIR.sub("papers", query, count=1)
    return list(zip(aliases, resolved)), clean_query


def _rank_scoped_pages(rows_by_mode: list[tuple[str, list[dict[str, Any]], float]],
                       parent_ids: dict[str, str], paper_id: str, alias: str,
                       limit: int, rrf_k: int = 60
                       ) -> list[dict[str, Any]]:
    chunk_scores: dict[str, float] = defaultdict(float)
    chunk_rows: dict[str, dict[str, Any]] = {}
    ranks: dict[tuple[str, int | None], dict[str, int]] = defaultdict(dict)
    children: dict[tuple[str, int | None], dict[str, dict[str, Any]]] = defaultdict(dict)
    for mode, rows, weight in rows_by_mode:
        scoped = [row for row in rows if row.get("paper_id") == paper_id]
        seen_pages: set[tuple[str, int | None]] = set()
        for rank, row in enumerate(scoped, 1):
            key = (row["sha256"], row.get("pdf_page"))
            children[key].setdefault(row["chunk_id"], row)
            chunk_rows[row["chunk_id"]] = row
            chunk_scores[row["chunk_id"]] += weight / (rrf_k + rank)
            if key in seen_pages:
                continue
            seen_pages.add(key)
            ranks[key][mode] = rank
    page_parents: dict[tuple[str, int | None], dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list))
    for key, page_children in children.items():
        for chunk_id in page_children:
            page_parents[key][parent_ids.get(chunk_id, chunk_rows[chunk_id].get(
                "parent_chunk_id", chunk_id))].append(chunk_id)
    scores: dict[tuple[str, int | None], float] = {}
    for key, parents in page_parents.items():
        parent_scores = sorted((max(chunk_scores[chunk_id] for chunk_id in chunk_ids)
                                for chunk_ids in parents.values()), reverse=True)
        scores[key] = sum(parent_scores[:2])
    ranked = sorted(scores, key=scores.get, reverse=True)
    result = []
    for rank, key in enumerate(ranked[:limit], 1):
        supporting = list(children[key].values())
        representative = max(supporting, key=lambda row: chunk_scores[row["chunk_id"]])
        row = dict(representative)
        row_parents = page_parents[key]
        row.update({"rank_score": scores[key], "page_rank_score": scores[key],
                    "source_paper_id": paper_id, "explicit_paper_alias": alias,
                    "source_local_page_rank": rank, "modality_page_ranks": ranks[key],
                    "parent_chunk_ids": list(row_parents),
                    "supporting_child_chunk_ids": list(children[key]),
                    "supporting_children": supporting})
        result.append(row)
    return result


def _parent_ids_for_rows(database: Path, rows: list[dict[str, Any]]) -> dict[str, str]:
    chunk_ids = list(dict.fromkeys(row["chunk_id"] for row in rows))
    if not chunk_ids:
        return {}
    conn = open_database(database, readonly=True)
    try:
        parent_ids = {}
        for offset in range(0, len(chunk_ids), 500):
            batch = chunk_ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            parent_ids.update({row["chunk_id"]: row["parent_chunk_id"] for row in conn.execute(
                f"SELECT chunk_id,parent_chunk_id FROM chunks WHERE chunk_id IN ({placeholders})", batch)})
        return parent_ids
    finally:
        conn.close()


def retrieve_explicit_two_paper_pages(database: Path, query: str, limit_per_paper: int = 10,
                                      artifact: Path | None = None, candidate_depth: int = 200
                                      ) -> list[dict[str, Any]]:
    """Return interleaved page candidates for two explicitly named papers.

    Paper aliases come from the query and indexed titles. Search candidates are
    generated before any gold-page comparison, then fused within each named paper.
    """
    if not query.strip() or limit_per_paper <= 0 or candidate_depth <= 0:
        return []
    resolved = resolve_explicit_paper_pair(database, query)
    if not resolved:
        return []
    papers, clean_query = resolved
    bm25 = bm25_search(database, clean_query, candidate_depth, source_type="original_pdf",
                       readonly=True)
    vector = vector_search(database, clean_query, candidate_depth, source_type="original_pdf",
                           artifact=artifact)
    parent_ids = _parent_ids_for_rows(database, [*bm25, *vector])
    by_paper = [
        _rank_scoped_pages([("bm25", bm25, 2.0), ("vector", vector, 0.5)], parent_ids,
                           paper_id, alias, limit_per_paper)
        for alias, paper_id in papers
    ]
    output: list[dict[str, Any]] = []
    for offset in range(limit_per_paper):
        for rows in by_paper:
            if offset < len(rows):
                output.append(rows[offset])
    return output


def rank_parent_pages(rows: list[dict[str, Any]], parent_ids: dict[str, str],
                      limit: int) -> list[dict[str, Any]]:
    """Aggregate child ranks to pages; count at most one child per parent in the score."""
    if limit <= 0:
        return []
    pages: dict[tuple[str, int | None], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list))
    for row in rows:
        key = (row["sha256"], row.get("pdf_page"))
        parent_id = parent_ids.get(row["chunk_id"], row.get("parent_chunk_id", row["chunk_id"]))
        pages[key][parent_id].append(row)

    ranked_pages = []
    for (sha256, page_number), parents in pages.items():
        parent_best = []
        all_children = []
        for parent_id, children in parents.items():
            children = sorted(children, key=lambda row: row.get("rank_score", 0.0), reverse=True)
            parent_best.append((children[0].get("rank_score", 0.0), parent_id, children[0]))
            all_children.extend(children)
        parent_best.sort(key=lambda item: item[0], reverse=True)
        score = sum(item[0] for item in parent_best[:2])
        representative = dict(parent_best[0][2])
        representative.update({
            "rank_score": score,
            "page_rank_score": score,
            "parent_chunk_ids": [item[1] for item in parent_best],
            "supporting_child_chunk_ids": [row["chunk_id"] for row in all_children],
            "supporting_children": all_children,
        })
        ranked_pages.append(representative)
    ranked_pages.sort(key=lambda row: row["page_rank_score"], reverse=True)
    return ranked_pages[:limit]


def retrieve_parent_pages(database: Path, query: str, limit: int = 10,
                          artifact: Path | None = None,
                          candidate_multiplier: int = 20) -> list[dict[str, Any]]:
    """Overfetch hybrid chunks, then rank unique pages by distinct parent evidence."""
    if not query.strip() or limit <= 0:
        return []
    pool_size = max(limit * candidate_multiplier, 40)
    rows = hybrid_search(database, query, limit=pool_size, artifact=artifact)
    if not rows:
        return []
    chunk_ids = list(dict.fromkeys(row["chunk_id"] for row in rows))
    conn = open_database(database, readonly=True)
    try:
        parent_ids: dict[str, str] = {}
        for offset in range(0, len(chunk_ids), 500):
            batch = chunk_ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            parent_ids.update({row["chunk_id"]: row["parent_chunk_id"] for row in conn.execute(
                f"SELECT chunk_id,parent_chunk_id FROM chunks WHERE chunk_id IN ({placeholders})", batch)})
    finally:
        conn.close()
    return rank_parent_pages(rows, parent_ids, limit)
