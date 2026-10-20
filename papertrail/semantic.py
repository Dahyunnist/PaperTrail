"""Optional local BGE semantic index and retrieval."""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from .retrieval import _revision, _rows, bm25_search

MODEL_ID = "BAAI/bge-small-zh-v1.5"
INDEX_FORMAT = 1
_INDEX_CACHE: dict[str, tuple[int, dict[str, Any]]] = {}


def _model_path() -> str:
    configured = os.environ.get("PAPERTRAIL_BGE_MODEL")
    if configured:
        return configured
    hub = Path.home() / ".cache" / "huggingface" / "hub" / "models--BAAI--bge-small-zh-v1.5" / "snapshots"
    snapshots = sorted((path for path in hub.iterdir() if path.is_dir()), key=lambda p: p.stat().st_mtime)
    if not snapshots:
        raise FileNotFoundError("未找到本机 BGE 模型；设置 PAPERTRAIL_BGE_MODEL 指向模型目录")
    return str(snapshots[-1])


@lru_cache(maxsize=1)
def _load_model():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(_model_path(), local_files_only=True, device="cpu")


def _encode(texts: list[str]) -> np.ndarray:
    return _load_model().encode(texts, batch_size=64, normalize_embeddings=True,
                        show_progress_bar=False, convert_to_numpy=True).astype(np.float32)


def build_bge_index(database: Path, artifact: Path) -> dict[str, Any]:
    rows = _rows(database)
    if not rows:
        raise ValueError("建立 BGE 索引至少需要一个文本块")
    texts = [f"为这个句子生成表示以用于检索相关文章：{row['title']}。{row['section_title']}。{row['body']}" for row in rows]
    vectors = _encode(texts)
    digest = hashlib.sha256("\n".join(row["chunk_id"] for row in rows).encode()).hexdigest()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"index_format": INDEX_FORMAT, "model_id": MODEL_ID, "chunk_digest": digest,
              "index_revision": _revision(database), "rows": rows, "vectors": vectors}
    joblib.dump(bundle, artifact)
    return {"chunks": len(rows), "dimensions": int(vectors.shape[1]), "model": MODEL_ID,
            "artifact": str(artifact)}


def _load(database: Path, artifact: Path) -> dict[str, Any]:
    key = str(artifact.resolve())
    revision = _revision(database)
    cached = _INDEX_CACHE.get(key)
    if cached and artifact.exists() and cached[0] == revision:
        return cached[1]
    if not artifact.exists():
        build_bge_index(database, artifact)
    bundle = joblib.load(artifact)
    rows = _rows(database)
    digest = hashlib.sha256("\n".join(row["chunk_id"] for row in rows).encode()).hexdigest()
    if (bundle.get("index_format") != INDEX_FORMAT or bundle.get("chunk_digest") != digest
            or bundle.get("index_revision") != revision):
        build_bge_index(database, artifact)
        bundle = joblib.load(artifact)
    _INDEX_CACHE[key] = (revision, bundle)
    return bundle


def bge_search(database: Path, query: str, limit: int = 5,
               source_type: str | None = None, artifact: Path | None = None) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    artifact = artifact or database.with_name(database.stem + ".bge.joblib")
    bundle = _load(database, artifact)
    query_vector = _encode([f"为这个句子生成表示以用于检索相关文章：{query}"])[0]
    scores = bundle["vectors"] @ query_vector
    order = np.argsort(scores)[::-1]
    result = []
    for ix in order:
        row = bundle["rows"][int(ix)]
        if source_type and row["source_type"] != source_type:
            continue
        result.append({"paper_id": row["paper_id"], "version_id": row["version_id"],
                       "sha256": row["sha256"], "source_type": row["source_type"],
                       "title": row["title"], "section": row["section_title"],
                       "pdf_page": row["page_number"], "path": row["absolute_path"],
                       "parse_status": row["parse_status"], "text_origin": row["text_origin"],
                       "rank_score": float(scores[int(ix)]), "text": row["body"],
                       "chunk_id": row["chunk_id"]})
        if len(result) >= limit:
            break
    return result


def hybrid_bge_search(database: Path, query: str, limit: int = 5,
                      source_type: str | None = None, artifact: Path | None = None) -> list[dict[str, Any]]:
    lexical = bm25_search(database, query, max(limit * 5, 30), source_type)
    semantic = bge_search(database, query, max(limit * 5, 30), source_type, artifact)
    fused: dict[str, dict[str, Any]] = {}
    for rows, signal, weight in ((lexical, "bm25", 2.0), (semantic, "bge", 1.0)):
        for rank, row in enumerate(rows, 1):
            item = fused.setdefault(row["chunk_id"], {**row, "rank_score": 0.0, "retrieval_signals": []})
            item["rank_score"] += weight / (60 + rank)
            item["retrieval_signals"].append(signal)
    return sorted(fused.values(), key=lambda row: row["rank_score"], reverse=True)[:limit]
