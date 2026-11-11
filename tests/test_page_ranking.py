from papertrail.page_ranking import rank_parent_pages


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
