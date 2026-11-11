"""Parent-aware page ranking for offline PT2 diagnostics."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from typing import Any

from .retrieval import hybrid_search
from .s1_index import open_database


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
