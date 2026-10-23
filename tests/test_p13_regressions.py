def test_short_evidence_statements_are_kept_for_fact_location():
    from papertrail.qa import _sentences

    assert _sentences("Driver names were not collected.") == ["Driver names were not collected."]


def test_unpunctuated_pdf_list_items_remain_citable():
    from papertrail.qa import _sentences

    text = "Methods\n- Save the raw data\ne) Record all steps used to process data"
    assert _sentences(text) == ["Save the raw data", "Record all steps used to process data"]


def test_plural_paper_questions_trigger_subquestion_decomposition():
    from papertrail.qa import _requires_decomposition

    assert _requires_decomposition(
        "How do the scientific-computing and numerical-data papers recommend supporting reproducibility?")
    assert _requires_decomposition(
        "What do the two computational-notebook papers recommend to help others reuse a project?")
    assert _requires_decomposition("这两篇论文分别提供什么建议？")
    assert not _requires_decomposition("What does the scientific-computing paper recommend?")
    assert not _requires_decomposition("Is the finding unrelated to the main question?")


def test_decomposed_same_paper_evidence_keeps_each_required_slot(tmp_path, monkeypatch):
    import papertrail.qa as qa
    from papertrail.s1_index import open_database

    db = tmp_path / "slots.sqlite3"
    open_database(db).close()
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "slot-test-model")
    subquestions = ["Alpha finding?", "Beta finding?", "Gamma finding?"]
    rows = {}
    for index, word in enumerate(("Alpha", "Beta", "Gamma"), 1):
        rows[f"{word} finding?"] = [{
            "chunk_id": f"chunk-{index}", "version_id": f"version-{index}",
            "paper_id": "one-paper", "sha256": "a" * 64, "source_type": "original_pdf",
            "title": "One Study", "section": "Results", "pdf_page": index,
            "path": "unused.pdf", "text_origin": "native_text", "rank_score": 1.0,
            "text": f"{word} finding is supported by direct evidence in this study.",
        }]
    monkeypatch.setattr(qa, "_plan_subquestions", lambda *_args: {
        "subquestions": subquestions, "usage": {},
    })
    monkeypatch.setattr(qa, "retrieve", lambda _db, query, *_args, **_kwargs: rows[query])
    monkeypatch.setattr(qa, "_screen_evidence", lambda _question, candidates, _model: {
        "relevant_ids": list(range(len(candidates))), "targeted_query": "",
        "sufficient": True, "usage": {},
    })
    monkeypatch.setattr(qa, "_validate_quote", lambda *_args: True)
    monkeypatch.setattr(qa, "_synthesize_local", lambda _question, evidence, _model, _subs: {
        "claims": [{"text": "All three findings are supported.", "evidence_ids": [0, 1, 2],
                    "subquestion_ids": [0, 1, 2], "support": "supported",
                    "relevant": True, "support_method": "test_judge"}],
        "coverage_complete": True, "covered_subquestions": [0, 1, 2],
        "coverage_requirements": subquestions, "coverage_gaps": [],
        "generation_retry_used": False, "usage": {},
    })

    result = qa.ask(db, "Compare these three findings.", limit=5, mode="bm25")

    assert result["status"] == "generated_claims_reviewed"
    assert len(result["claims"][0]["support_evidence"]) == 3
    assert result["missing_subquestions"] == []


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


def test_claim_cannot_cover_subquestion_with_evidence_from_another_slot(monkeypatch):
    import papertrail.qa as qa

    outputs = iter([
        {"claims": [{"text": "Paper B reports a result.", "evidence_ids": [0],
                     "subquestion_ids": [1]}]},
        {"results": [{"claim_id": 0, "supported": True, "relevant": True}],
         "coverage_requirements": ["Paper A method", "Paper B result"],
         "covered_subquestions": [0, 1], "coverage_complete": True, "coverage_gaps": []},
    ])
    monkeypatch.setattr(qa, "chat_json", lambda *_args, **_kwargs: next(outputs))

    result = qa._synthesize_local("Compare Paper A and Paper B.", [{
        "quote": "Paper A uses calibration.", "title": "Paper A", "pdf_page": 1,
        "subquestion_ids": [0],
    }], "test-model", ["What method does Paper A use?", "What result does Paper B report?"])

    assert result["claims"][0]["support"] == "supported"
    assert result["claims"][0]["evidence_mapping_valid"] is False
    assert result["coverage_complete"] is False
    assert any("引文槽位" in gap for gap in result["coverage_gaps"])


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
