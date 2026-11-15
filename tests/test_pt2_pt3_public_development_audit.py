import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_pt2_pt3_public_development.py"
SPEC = importlib.util.spec_from_file_location("evaluate_pt2_pt3_public_development", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_public_development_audit_scope_and_no_model_guard():
    report = audit.run()
    assert report["scope"]["groups"] == ["pt7", "pt8", "pt10", "pt11"]
    assert report["scope"]["fresh_temporary_indexes"] is True
    assert report["scope"]["model_calls"] == 0
    assert all(group["indexed_public_pdfs"] == 3 for group in report["groups"])
    assert report["schema_version"] == 4
    assert report["refusal_quality"]["status"] == "not_assessed_without_generation"
    assert report["answer_correctness"]["status"] == "not_assessed_without_generation_or_human_review"
    assert all("heldout" not in group["group_id"] for group in report["groups"])
    assert report["scope"]["extractive_qa_mode"] == "bm25"
    groups = {group["group_id"].split("-")[0]: group for group in report["groups"]}
    cross_paper = [groups[group]["by_question_type"]["cross_paper"]
                   for group in ("pt7", "pt10", "pt11")]
    assert sum(row["qa_candidate_page_slots"] for row in cross_paper) >= sum(
        row["cited_gold_page_slots"] for row in cross_paper)
    assert sum(row["citation_contains_gold_phrase_slots"] for row in cross_paper) == 0
    assert sum(row["gold_quotes_on_registered_pdf_pages"] for row in cross_paper) == 6
    assert sum(row["gold_quotes_in_indexed_chunks"] for row in cross_paper) == 6
    assert sum(row["qa_candidate_gold_phrase_chunks"] for row in cross_paper) == 2
    assert sum(row["extractive_candidate_gold_phrase_slots"] for row in cross_paper) == 2
    assert sum(row["quote_validated_gold_phrase_slots"] for row in cross_paper) == 0
    assert sum(row["quote_validation_rejected_gold_phrase_slots"] for row in cross_paper) == 0
    assert sum(row["paper_quote_limit_skipped_gold_phrase_slots"] for row in cross_paper) == 2
    assert sum(row["duplicate_quote_skipped_gold_phrase_slots"] for row in cross_paper) == 0
    assert sum(row["citation_limit_truncated_gold_phrase_slots"] for row in cross_paper) == 0
    assert sum(row["citation_chunk_metadata_valid"] for row in cross_paper) == 13
    assert sum(row["citation_quote_in_indexed_chunk"] for row in cross_paper) == 13
    assert sum(row["citation_source_validation_failures"] for row in cross_paper) == 0
    unanswerable = [group["by_question_type"]["unanswerable"] for group in report["groups"]
                    if "unanswerable" in group["by_question_type"]]
    assert len(unanswerable) == 2
    assert all(row["unanswerable_with_extractive_candidates"] == 1 for row in unanswerable)
    for group in report["groups"]:
        assert len(group["by_question"]) == group["question_count"]
        assert [row["question_index"] for row in group["by_question"]] == list(
            range(1, group["question_count"] + 1))
        assert all("question" not in row and "quote" not in row and "evidence" not in row
                   for row in group["by_question"])
        for row in group["by_question"]:
            assert row["retrieval_mode"] == "bm25"
            assert row["index_revision_consistent"] is True
            assert len(row["query_hash"]) == 64
            assert row["candidate_chunk_ids"]
            assert set(row["citation_chunk_ids"]).issubset(row["candidate_chunk_ids"])
            assert set(row["extractive_candidate_chunk_ids"]).issubset(row["candidate_chunk_ids"])
            assert set(row["quote_validated_chunk_ids"]).issubset(row["extractive_candidate_chunk_ids"])
            assert set(row["citation_chunk_ids"]).issubset(row["quote_validated_chunk_ids"])
            assert "extractive_candidate_quotes" not in row
    cross_rows = [row for group in report["groups"] for row in group["by_question"]
                  if row["question_type"] == "cross_paper"]
    sentence_ranks = [rank for row in cross_rows
                      for rank in row["gold_phrase_sentence_candidate_ranks"] if rank is not None]
    assert sentence_ranks == [52, 30]


def test_public_development_audit_labels_only_offline_bm25_modes():
    import pytest
    with pytest.raises(ValueError, match="only offline BM25 modes"):
        audit.run(qa_mode="model")


def test_public_development_audit_rejects_network_and_model_imports():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    forbidden = {"requests", "httpx", "urllib", "socket", "aiohttp", "websocket"}
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection(forbidden)
