def test_short_evidence_statements_are_kept_for_fact_location():
    from papertrail.qa import _sentences

    assert _sentences("Driver names were not collected.") == ["Driver names were not collected."]


def test_invalid_subquestion_ids_get_one_structured_repair_retry(monkeypatch):
    import papertrail.qa as qa

    outputs = iter([
        {"claims": [{"text": "Paper A reports 18 minutes.", "evidence_ids": [0],
                     "subquestion_ids": ["0"]}], "_usage": {"prompt_eval_count": 10}},
        {"claims": [{"text": "Paper A reports 18 minutes.", "evidence_ids": [0],
                     "subquestion_ids": [0]}], "_usage": {"prompt_eval_count": 12}},
        {"results": [{"claim_id": 0, "supported": True, "relevant": True}],
         "coverage_requirements": ["Paper A median", "Paper A sample size"], "covered_subquestions": [0],
         "coverage_complete": True, "coverage_gaps": [], "_usage": {"prompt_eval_count": 14}},
    ])
    calls = []

    def fake_chat(_model, _system, prompt, **_kwargs):
        calls.append(prompt)
        return next(outputs)

    monkeypatch.setattr(qa, "chat_json", fake_chat)
    result = qa._synthesize_local("What median does Paper A report?", [{
        "quote": "The median scan-to-door time was 18 minutes.", "title": "Paper A", "pdf_page": 1,
        "subquestion_ids": [0],
    }], "test-model", ["What median does Paper A report?", "How many deliveries were included?"])

    assert len(calls) == 3
    assert result["generation_retry_used"] is True
    assert result["claims"][0]["subquestion_ids"] == [0]
    assert result["claims"][0]["support"] == "supported"


def test_invalid_evidence_reference_gets_one_schema_repair_retry(monkeypatch):
    import papertrail.qa as qa

    outputs = iter([
        {"claims": [{"text": "The median was 18 minutes.", "evidence_ids": [4]}]},
        {"claims": [{"text": "The median was 18 minutes.", "evidence_ids": [0]}]},
        {"results": [{"claim_id": 0, "supported": True, "relevant": True}],
         "coverage_complete": True, "coverage_requirements": ["median"], "coverage_gaps": []},
    ])
    monkeypatch.setattr(qa, "chat_json", lambda *_args, **_kwargs: next(outputs))
    result = qa._synthesize_local("What was the median?", [{
        "quote": "The median scan-to-door time was 18 minutes.", "title": "Study A", "pdf_page": 1,
    }], "test-model")

    assert result["generation_retry_used"] is True
    assert result["claims"][0]["evidence_ids"] == [0]
    assert result["claims"][0]["support"] == "supported"
