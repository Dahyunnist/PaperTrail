from pathlib import Path

from papertrail import semantic


def test_page_reranker_reorders_unique_pages_and_validates_ids(monkeypatch):
    rows = [
        {"sha256": "a" * 64, "pdf_page": 1, "chunk_id": "a1", "title": "Paper A",
         "text": "off-topic excerpt", "text_origin": "native_text", "rank_score": 0.1},
        {"sha256": "b" * 64, "pdf_page": 2, "chunk_id": "b2", "title": "Paper B",
         "text": "directly answers the question", "text_origin": "native_text", "rank_score": 0.09},
        {"sha256": "a" * 64, "pdf_page": 1, "chunk_id": "a2", "title": "Paper A",
         "text": "duplicate page chunk", "text_origin": "native_text", "rank_score": 0.08},
    ]
    monkeypatch.setattr(semantic, "hybrid_bge_search", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr("papertrail.local_llm.configured_model", lambda: "rerank-test")
    monkeypatch.setattr("papertrail.local_llm.chat_json", lambda *_args, **_kwargs: {
        "page_order": [1, 0], "_usage": {"prompt_eval_count": 8}})
    result = semantic.llm_rerank_search(Path("db.sqlite3"), "question", limit=2)
    assert [row["sha256"] for row in result] == ["b" * 64, "a" * 64]
    assert result[0]["retrieval_signals"][-1] == "llm_rerank"
    assert result[0]["rerank_usage"]["prompt_eval_count"] == 8


def test_page_reranker_falls_back_and_marks_invalid_order(monkeypatch):
    rows = [{"sha256": str(index) * 64, "pdf_page": 1, "chunk_id": str(index),
             "title": "Paper", "text": "evidence", "text_origin": "native_text"} for index in (1, 2)]
    monkeypatch.setattr(semantic, "hybrid_bge_search", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr("papertrail.local_llm.configured_model", lambda: "rerank-test")
    monkeypatch.setattr("papertrail.local_llm.chat_json", lambda *_args, **_kwargs: {"page_order": [0, 0]})
    result = semantic.llm_rerank_search(Path("db.sqlite3"), "question")
    assert len(result) == 2
    assert result[0]["rerank_error"] == "LLM reranker returned invalid page_order"
    assert result[0]["retrieval_signals"][-1] == "rerank_fallback"


def test_wide_page_search_expands_same_candidate_pool_and_deduplicates(monkeypatch):
    seen = {}
    rows = [{"sha256": "a" * 64, "pdf_page": 1, "chunk_id": "a1", "text_origin": "native_text"},
            {"sha256": "a" * 64, "pdf_page": 1, "chunk_id": "a2", "text_origin": "native_text"},
            {"sha256": "b" * 64, "pdf_page": 2, "chunk_id": "b2", "text_origin": "native_text"}]

    def search(_db, _query, limit, *_args):
        seen["candidate_chunks"] = limit
        return rows

    monkeypatch.setattr(semantic, "hybrid_bge_search", search)
    result = semantic.hybrid_bge_wide_search(Path("db.sqlite3"), "query", limit=5)
    assert seen["candidate_chunks"] == 100
    assert [row["sha256"] for row in result] == ["a" * 64, "b" * 64]


def test_dense_reranker_sorts_hybrid_candidates_by_bge_similarity(monkeypatch):
    rows = [
        {"chunk_id": "low", "sha256": "a" * 64, "pdf_page": 1,
         "text_origin": "native_text", "retrieval_signals": ["bm25", "bge"]},
        {"chunk_id": "high", "sha256": "b" * 64, "pdf_page": 2,
         "text_origin": "native_text", "retrieval_signals": ["bge"]},
    ]
    bundle_rows = [{"chunk_id": "low"}, {"chunk_id": "high"}]
    monkeypatch.setattr(semantic, "hybrid_bge_search", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(semantic, "_load", lambda *_args: {
        "rows": bundle_rows, "vectors": semantic.np.array([[0.1, 0.0], [0.9, 0.0]])})
    monkeypatch.setattr(semantic, "_encode", lambda *_args: semantic.np.array([[1.0, 0.0]]))
    result = semantic.hybrid_bge_dense_rerank_search(Path("db.sqlite3"), "question", limit=2)
    assert [row["chunk_id"] for row in result] == ["high", "low"]
    assert result[0]["retrieval_signals"][-1] == "bge_dense_rerank"
