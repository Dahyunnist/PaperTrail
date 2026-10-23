"""Local latent-vector and reciprocal-rank-fusion retrieval for S2."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .s1_index import open_database, search as bm25_search, search_or as bm25_or_search

VECTOR_INDEX_FORMAT = 2
QUESTION_STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "does", "for", "from",
                      "how", "in", "is", "it", "of", "on", "or", "the", "their", "this",
                      "to", "what", "when", "which", "with", "why", "data", "paper", "study",
                      "method", "model", "approach", "result", "的", "了", "吗", "如何", "什么"}
_BUNDLE_CACHE: dict[str, tuple[int, dict[str, Any]]] = {}


def _expanded_bm25_search(database: Path, query: str, limit: int,
                          source_type: str | None) -> list[dict[str, Any]]:
    pool_size = max(limit * 4, 20)
    exact = bm25_search(database, query, pool_size, source_type)
    terms = list(dict.fromkeys(term for term in re.findall(r"[\w]+", query.casefold())
                               if term not in QUESTION_STOPWORDS and len(term) > 1))
    expanded = bm25_or_search(database, " ".join(terms), pool_size, source_type) if terms else []
    combined: dict[str, dict[str, Any]] = {}
    for rows, weight, signal in ((exact, 2.0, "bm25_and"), (expanded, 1.0, "bm25_or")):
        chunk_rows = []
        seen_chunks = set()
        for rank, row in enumerate(rows, 1):
            chunk_key = row["chunk_id"]
            if chunk_key in seen_chunks:
                continue
            seen_chunks.add(chunk_key)
            chunk_rows.append((rank, row))
        for rank, row in chunk_rows:
            key = row["chunk_id"]
            item = combined.setdefault(key, {**row, "rank_score": 0.0,
                                               "retrieval_signals": []})
            item["rank_score"] += weight / (60 + rank)
            item["retrieval_signals"].append(signal)
    return sorted(combined.values(), key=lambda item: item["rank_score"], reverse=True)[:limit]


def _vector_dependencies():
    """Load dependencies used only by latent-vector retrieval."""
    try:
        import joblib
        import numpy as np
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
    except ImportError as exc:
        raise RuntimeError(
            "向量检索需要安装 requirements-dev.txt 中的 numpy、joblib 和 scikit-learn"
        ) from exc
    return joblib, np, TruncatedSVD, TfidfVectorizer, normalize


def _rows(database: Path) -> list[dict[str, Any]]:
    conn = open_database(database)
    try:
        return [dict(row) for row in conn.execute(
            "SELECT c.chunk_id,c.version_id,c.source_type,c.title,c.section_title,c.page_number,c.text_origin,c.body,"
            "p.paper_id,v.sha256,v.parse_status,l.absolute_path "
            "FROM chunks c JOIN paper_versions v ON v.version_id=c.version_id "
            "JOIN papers p ON p.paper_id=v.paper_id "
            "JOIN source_locations l ON l.version_id=v.version_id "
            "GROUP BY c.chunk_id ORDER BY c.chunk_id")]
    finally:
        conn.close()


def _revision(database: Path) -> int:
    conn = open_database(database)
    try:
        return int(conn.execute("SELECT value FROM app_metadata WHERE key='index_revision'").fetchone()[0])
    finally:
        conn.close()


def build_vector_index(database: Path, artifact: Path) -> dict[str, Any]:
    joblib, np, TruncatedSVD, TfidfVectorizer, normalize = _vector_dependencies()
    rows = _rows(database)
    if len(rows) < 2:
        raise ValueError("建立向量索引至少需要两个文本块")
    digest = hashlib.sha256("\n".join(row["chunk_id"] for row in rows).encode()).hexdigest()
    texts = [f"{row['title']} {row['section_title']} {row['body']}" for row in rows]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=2,
                                 max_features=120_000, sublinear_tf=True, dtype=np.float32)
    matrix = vectorizer.fit_transform(texts)
    dimensions = min(96, matrix.shape[0] - 1, matrix.shape[1] - 1)
    if dimensions < 2:
        raise ValueError("文本词项不足，无法建立潜在向量")
    reducer = TruncatedSVD(n_components=dimensions, random_state=42, n_iter=7)
    vectors = normalize(reducer.fit_transform(matrix)).astype(np.float32)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    revision = _revision(database)
    joblib.dump({"index_format": VECTOR_INDEX_FORMAT, "chunk_digest": digest,
                 "index_revision": revision, "rows": rows, "vectorizer": vectorizer,
                 "reducer": reducer, "vectors": vectors,
                 "explained_variance": float(reducer.explained_variance_ratio_.sum())}, artifact)
    _BUNDLE_CACHE[str(artifact.resolve())] = (revision, joblib.load(artifact))
    return {"chunks": len(rows), "dimensions": dimensions,
            "explained_variance": float(reducer.explained_variance_ratio_.sum()),
            "artifact": str(artifact)}


def _load_index(database: Path, artifact: Path) -> dict[str, Any]:
    joblib, _, _, _, _ = _vector_dependencies()
    cache_key = str(artifact.resolve())
    revision = _revision(database)
    cached = _BUNDLE_CACHE.get(cache_key)
    if cached and artifact.exists() and cached[0] == revision:
        return cached[1]
    rows = _rows(database)
    digest = hashlib.sha256("\n".join(row["chunk_id"] for row in rows).encode()).hexdigest()
    if not artifact.exists():
        build_vector_index(database, artifact)
    bundle = joblib.load(artifact)
    if bundle.get("index_revision", revision) != revision or bundle["chunk_digest"] != digest:
        build_vector_index(database, artifact)
        bundle = joblib.load(artifact)
    else:
        bundle["index_revision"] = revision
        if bundle.get("index_format") != VECTOR_INDEX_FORMAT:
            bundle["rows"] = rows
            bundle["index_format"] = VECTOR_INDEX_FORMAT
            joblib.dump(bundle, artifact)
    _BUNDLE_CACHE[cache_key] = (revision, bundle)
    return bundle


def vector_search(database: Path, query: str, limit: int = 5,
                  source_type: str | None = None,
                  artifact: Path | None = None) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    _, np, _, _, normalize = _vector_dependencies()
    artifact = artifact or database.with_name(database.stem + ".vectors.joblib")
    bundle = _load_index(database, artifact)
    query_vector = bundle["reducer"].transform(bundle["vectorizer"].transform([query]))
    query_vector = normalize(query_vector).astype(np.float32)
    scores = bundle["vectors"] @ query_vector.T
    order = np.asarray(scores).reshape(-1).argsort()[::-1]
    result = []
    for index in order:
        row = bundle["rows"][int(index)]
        if source_type and row["source_type"] != source_type:
            continue
        result.append({"paper_id": row["paper_id"], "version_id": row["version_id"],
                       "sha256": row["sha256"], "source_type": row["source_type"],
                       "title": row["title"], "section": row["section_title"],
                       "pdf_page": row["page_number"], "path": row["absolute_path"],
                       "parse_status": row["parse_status"], "text_origin": row["text_origin"],
                       "rank_score": float(scores[int(index), 0]),
                       "text": row["body"], "chunk_id": row["chunk_id"]})
        if len(result) == limit:
            break
    return result


def hybrid_search(database: Path, query: str, limit: int = 5,
                  source_type: str | None = None, rrf_k: int = 60,
                  bm25_weight: float = 2.0, vector_weight: float = 0.5,
                  artifact: Path | None = None) -> list[dict[str, Any]]:
    lexical = bm25_search(database, query, max(limit * 4, 20), source_type)
    latent = vector_search(database, query, max(limit * 4, 20), source_type, artifact)
    combined: dict[str, dict[str, Any]] = {}
    for ranked, weight in ((lexical, bm25_weight), (latent, vector_weight)):
        for rank, row in enumerate(ranked, 1):
            item = combined.setdefault(row["chunk_id"], {**row, "rank_score": 0.0,
                                                           "retrieval_signals": []})
            item["rank_score"] += weight / (rrf_k + rank)
            item["retrieval_signals"].append("bm25" if ranked is lexical else "latent_vector")
    ordered = sorted(combined.values(), key=lambda item: item["rank_score"], reverse=True)
    return ordered[:limit]


def retrieve(database: Path, query: str, limit: int = 5,
             source_type: str | None = None, mode: str = "bm25",
             artifact: Path | None = None) -> list[dict[str, Any]]:
    if mode == "bm25":
        return bm25_search(database, query, limit, source_type)
    if mode == "bm25_expanded":
        return _expanded_bm25_search(database, query, limit, source_type)
    if mode == "vector":
        return vector_search(database, query, limit, source_type, artifact)
    if mode == "hybrid":
        return hybrid_search(database, query, limit, source_type, artifact=artifact)
    if mode in {"bge", "hybrid_bge", "hybrid_bge_wide", "hybrid_bge_dense_rerank", "hybrid_bge_rerank"}:
        from .semantic import (bge_search, hybrid_bge_search, hybrid_bge_wide_search,
                               hybrid_bge_dense_rerank_search, llm_rerank_search)
        fn = {"bge": bge_search, "hybrid_bge": hybrid_bge_search,
              "hybrid_bge_wide": hybrid_bge_wide_search,
              "hybrid_bge_dense_rerank": hybrid_bge_dense_rerank_search,
              "hybrid_bge_rerank": llm_rerank_search}[mode]
        return fn(database, query, limit, source_type, artifact)
    raise ValueError(f"未知检索模式：{mode}")
