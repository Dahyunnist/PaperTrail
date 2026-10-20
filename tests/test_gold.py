from pathlib import Path

from papertrail.gold import _normalize_excerpt, load_gold, verify_quotes


PROJECT = Path(__file__).resolve().parents[1]


def test_gold_schema_and_manual_pdf_quotes():
    sources = PROJECT / "configs" / "sources.example.yaml"
    gold = load_gold(PROJECT / "evals" / "gold.jsonl")
    assert len(gold) == 34
    assert {item["question_type"] for item in gold} == {
        "fact_location", "method_comparison", "cross_paper", "multi_hop", "conflict", "unanswerable"
    }
    assert len({e["file_name"] for item in gold for e in item["evidence"]}) == 10
    assert verify_quotes(gold, sources) == 37


def test_gold_rejects_unanswerable_questions_with_supporting_quotes(tmp_path):
    invalid = tmp_path / "bad.jsonl"
    invalid.write_text(
        '{"id":"x","question_type":"unanswerable","question":"Q?",'
        '"expected_answer":"A","abstain":true,"evidence":[{}]}\n',
        encoding="utf-8",
    )
    try:
        load_gold(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid unanswerable evidence was accepted")


def test_quote_normalization_joins_hyphenated_line_wraps():
    assert _normalize_excerpt("membership in- ference attack") == \
        _normalize_excerpt("membership inference attack")
