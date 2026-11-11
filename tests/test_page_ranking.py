from papertrail.page_ranking import rank_parent_pages
from papertrail.page_ranking import retrieve_explicit_two_paper_pages
from papertrail.s1_index import open_database


def _row(chunk, paper, sha, page, parent, score):
    return {"chunk_id": chunk, "paper_id": paper, "sha256": sha, "pdf_page": page,
            "parent_chunk_id": parent, "rank_score": score, "text": f"evidence-{chunk}"}


def test_parent_page_ranking_preserves_children_and_separates_papers():
    rows = [
        _row("a-1", "paper-a", "a" * 64, 1, "parent-a1", 0.10),
        _row("a-2", "paper-a", "a" * 64, 1, "parent-a1", 0.09),
        _row("a-3", "paper-a", "a" * 64, 1, "parent-a2", 0.08),
        _row("b-1", "paper-b", "b" * 64, 1, "parent-b1", 0.15),
        _row("b-2", "paper-b", "b" * 64, 2, "parent-b2", 0.12),
    ]

    ranked = rank_parent_pages(rows, {}, limit=3)

    assert [(row["sha256"], row["pdf_page"]) for row in ranked] == [
        ("a" * 64, 1), ("b" * 64, 1), ("b" * 64, 2)]
    first = ranked[0]
    assert first["page_rank_score"] == 0.18  # sibling a-2 cannot double-count parent-a1
    assert first["supporting_child_chunk_ids"] == ["a-1", "a-2", "a-3"]
    assert {row["chunk_id"] for row in first["supporting_children"]} == {"a-1", "a-2", "a-3"}
    assert first["chunk_id"] == "a-1"  # representative remains a source-verifiable child


def test_parent_page_ranking_nonpositive_limit_is_empty():
    assert rank_parent_pages([_row("c", "paper-c", "c" * 64, 1, "p", 1.0)], {}, 0) == []
    assert rank_parent_pages([_row("c", "paper-c", "c" * 64, 1, "p", 1.0)], {}, -1) == []


def test_explicit_two_paper_retrieval_cleans_aliases_and_round_robins(tmp_path, monkeypatch):
    import papertrail.page_ranking as page_ranking

    database = tmp_path / "library.sqlite3"
    conn = open_database(database)
    for paper_id, title, suffix in (("paper-a", "Alpha Lab", "a"),
                                    ("paper-b", "Beta Study", "b")):
        conn.execute("INSERT INTO papers(paper_id,title_candidate,identity_basis,identity_value) "
                     "VALUES(?,?,?,?)", (paper_id, title, "test", paper_id))
        conn.execute(
            "INSERT INTO paper_versions(version_id,paper_id,sha256,source_type,file_name,file_size,"
            "page_count,parseable_pages,low_text_pages_json,parse_status,doi_candidates_json,"
            "parser_version,indexed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"version-{suffix}", paper_id, suffix * 64, "original_pdf", f"{suffix}.pdf", 1,
             1, 1, "[]", "parsed", "[]", "test", "2026-01-01"),
        )
    conn.commit()
    conn.close()

    rows = [
        _row("a-1", "paper-a", "a" * 64, 1, "a-parent-1", 0.0),
        _row("a-1-sibling", "paper-a", "a" * 64, 1, "a-parent-1", 0.0),
        _row("a-2", "paper-a", "a" * 64, 2, "a-parent-2", 0.0),
        _row("b-1", "paper-b", "b" * 64, 1, "b-parent-1", 0.0),
        _row("b-2", "paper-b", "b" * 64, 2, "b-parent-2", 0.0),
    ]
    seen_queries = []

    def fake_bm25(_database, query, _limit, **_kwargs):
        seen_queries.append(query)
        return rows

    monkeypatch.setattr(page_ranking, "bm25_search", fake_bm25)
    monkeypatch.setattr(page_ranking, "vector_search", lambda *_args, **_kwargs: rows)
    results = retrieve_explicit_two_paper_pages(
        database, "What matters, both the alpha-lab and beta-study papers?", limit_per_paper=2)

    assert seen_queries == ["What matters, papers?"]
    assert [(row["paper_id"], row["pdf_page"]) for row in results] == [
        ("paper-a", 1), ("paper-b", 1), ("paper-a", 2), ("paper-b", 2)]
    assert all(row["supporting_child_chunk_ids"] for row in results)
    assert results[0]["parent_chunk_ids"] == ["a-parent-1"]
    assert set(results[0]["supporting_child_chunk_ids"]) == {"a-1", "a-1-sibling"}


def test_explicit_two_paper_strategy_remains_opt_in(monkeypatch, tmp_path):
    import papertrail.retrieval as retrieval

    marker = [{"chunk_id": "default-result"}]
    monkeypatch.setattr(retrieval, "hybrid_search",
                        lambda *_args, **_kwargs: marker)

    assert retrieval.retrieve(tmp_path / "unused.sqlite3",
                              "question about alpha-lab and beta-study papers",
                              limit=10, mode="hybrid") is marker
