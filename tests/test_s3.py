import json
from pathlib import Path

import fitz
import yaml

from papertrail.audit import _hash
from papertrail.qa import ask, conversation_history
from papertrail.s1_index import index_selection


def _make_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "CTGAN Mixed Data Generation", fontsize=16)
    page.insert_text((40, 100),
                     "CTGAN evaluates mixed continuous and discrete columns with reliable likelihood and utility measurements.",
                     fontsize=11)
    doc.save(path)
    doc.close()


def _indexed_db(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "corpus" / "ctgan.pdf"
    _make_pdf(source)
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "papers", "path": str(source.parent)}]}), encoding="utf-8")
    manifest = tmp_path / "selection.jsonl"
    manifest.write_text(json.dumps({"root_id": "papers", "file_name": source.name,
                                    "relative_path": source.name, "sha256": _hash(source),
                                    "kind": "pdf", "source_type": "original_pdf"}) + "\n", encoding="utf-8")
    db = tmp_path / "local" / "papers.sqlite3"
    assert index_selection(db, config, manifest)["added"] == 1
    return db, source


def test_qa_claims_are_exact_validated_and_persisted(tmp_path):
    db, source = _indexed_db(tmp_path)
    first = ask(db, "What does CTGAN evaluate?")
    assert first["status"] == "verified_excerpts"
    assert first["claims"]
    citation = first["claims"][0]["evidence"]
    assert citation["text_origin"] == "native_text"
    assert citation["sha256"] == _hash(source)
    with fitz.open(source) as doc:
        page = " ".join(doc[citation["pdf_page"] - 1].get_text("text").split()).casefold()
    assert " ".join(citation["quote"].split()).casefold() in page

    follow_up = ask(db, "And its columns?", first["conversation_id"])
    assert follow_up["context_query"] == first["question"]
    history = conversation_history(db, first["conversation_id"])
    assert len(history) == 2
    assert all(turn["claims"] for turn in history)

    source.write_bytes(source.read_bytes() + b"tampered")
    stale = ask(db, "What does CTGAN evaluate?")
    assert stale["status"] == "abstained"
    assert stale["claims"] == []


def test_local_llm_claims_require_verified_citations_and_support_review(tmp_path, monkeypatch):
    import papertrail.qa as qa

    db, _ = _indexed_db(tmp_path)
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "local-test")
    monkeypatch.setattr(qa, "_synthesize_local", lambda question, evidence, model: {"claims": [
        {"text": "CTGAN evaluates column utility.", "evidence_ids": [0], "support": "supported",
         "support_method": "local_llm_judge"},
        {"text": "CTGAN proves universal privacy.", "evidence_ids": [0], "support": "unsupported",
         "support_method": "local_llm_judge"},
    ], "usage": {"eval_count": 12}})
    result = ask(db, "What does CTGAN evaluate?")
    assert result["status"] == "generated_claims_reviewed"
    assert [claim["text"] for claim in result["claims"]] == ["CTGAN evaluates column utility."]
    history = conversation_history(db, result["conversation_id"])
    claim_evidence = history[0]["claims"][0]["evidence"]
    assert claim_evidence["support"] == "supported"
    assert claim_evidence["support_method"] == "local_llm_judge"
    assert result["usage"]["eval_count"] == 12


def test_evidence_screen_returns_relevant_ids_and_focused_query(monkeypatch):
    import papertrail.qa as qa

    monkeypatch.setattr(qa, "chat_json", lambda *_args, **_kwargs: {
        "relevant_ids": [1], "targeted_query": "utility under label noise", "sufficient": False,
        "_usage": {"eval_count": 8},
    })
    rows = [{"title": "Paper", "pdf_page": 2, "text": "Snippet"},
            {"title": "Paper", "pdf_page": 7, "text": "Relevant snippet"}]
    result = qa._screen_evidence("What changes under label noise?", rows, "test-model")
    assert result["relevant_ids"] == [1]
    assert result["targeted_query"] == "utility under label noise"
    assert result["sufficient"] is False


def test_candidate_excerpt_keeps_relevant_sentence_after_long_prefix():
    import papertrail.qa as qa

    text = ("This paper introduces a broad experimental framework and provides general background "
            "for evaluation across several research settings. "
            "For tabular data, the method uses online gradient descent to adapt parameters under label noise.")
    excerpt = qa._candidate_excerpt("How does the method adapt parameters under label noise?", text)

    assert "online gradient descent" in excerpt
    assert len(excerpt) <= 480


def test_claim_review_tracks_relevance_and_complete_coverage(monkeypatch):
    import papertrail.qa as qa

    outputs = iter([
        {"claims": [{"text": "It uses utility metrics.", "evidence_ids": [0]}],
         "_usage": {"eval_count": 4}},
        {"results": [{"claim_id": 0, "supported": True, "relevant": True}],
         "coverage_complete": False, "coverage_requirements": ["required detail"],
         "coverage_gaps": ["missing detail"], "_usage": {"eval_count": 5}},
    ])
    monkeypatch.setattr(qa, "chat_json", lambda *_args, **_kwargs: next(outputs))
    evidence = [{"quote": "The method measures utility with downstream tasks.",
                 "title": "Paper", "pdf_page": 3}]
    result = qa._synthesize_local("How does it evaluate utility?", evidence, "test-model")
    assert result["claims"][0]["support"] == "supported"
    assert result["claims"][0]["relevant"] is True
    assert result["coverage_complete"] is False
    assert result["coverage_gaps"] == ["missing detail"]
    assert result["coverage_requirements"] == ["required detail"]


def test_hosted_synthesis_keeps_full_method_sentence(monkeypatch):
    import json
    import papertrail.qa as qa

    monkeypatch.setenv("PAPERTRAIL_LLM_PROVIDER", "openai-compatible")
    quote = ("We proposed an online procedure for label shift adaptation that combines histogram binning, "
             "online label distribution estimation via Soft-Bayes, and model parameter adaptation via online gradient descent.")
    outputs = iter([
        {"claims": [{"text": "It uses online gradient descent.", "evidence_ids": [0]}]},
        {"results": [{"claim_id": 0, "supported": True, "relevant": True}],
         "coverage_complete": True, "coverage_requirements": ["online gradient descent"],
         "coverage_gaps": []},
    ])
    prompts = []
    def mock_chat(_model, _system, prompt, **_kwargs):
        prompts.append(json.loads(prompt))
        return next(outputs)
    monkeypatch.setattr(qa, "chat_json", mock_chat)
    qa._synthesize_local("Which method updates model parameters?", [{
        "quote": quote, "title": "Online label shift", "pdf_page": 8}], "test-model")
    assert prompts[0]["evidence"][0]["quote"] == quote


def test_hosted_prompt_budget_compacts_candidates_before_provider_call():
    import papertrail.qa as qa

    system = "screening system prompt"
    payload = {"question": "Which result is reported?", "candidates": [
        {"id": index, "title": f"Paper {index}", "text": (f"Evidence sentence {index}. " * 20),
         "page": index + 1}
        for index in range(12)
    ]}

    prompt = qa._hosted_json_prompt(system, payload)

    assert len(system) + len(prompt) <= qa._HOSTED_PROMPT_TARGET
    assert 1 <= len(payload["candidates"]) < 12
    assert all(candidate["text"] for candidate in payload["candidates"])


def test_hosted_prompt_compaction_preserves_each_subquestion_slot():
    import papertrail.qa as qa

    system = "screening system prompt"
    payload = {"question": "Compare all four studies.", "candidates": [
        {"id": index, "title": f"Paper {index}", "text": (f"Evidence sentence {index}. " * 35),
         "subquestion_ids": [index // 3]}
        for index in range(12)
    ]}

    prompt = qa._hosted_json_prompt(system, payload)

    assert len(system) + len(prompt) <= qa._HOSTED_PROMPT_TARGET
    assert {slot for row in payload["candidates"] for slot in row["subquestion_ids"]} == {0, 1, 2, 3}


def test_exact_serial_question_requires_a_cited_serial_value():
    import papertrail.qa as qa

    question = "What exact GPU serial number did the authors report?"
    assert qa._exact_serial_not_found(question, [{"quote": "All experiments used NVIDIA T4 16GB GPUs."}])
    assert not qa._exact_serial_not_found(question, [{"quote": "GPU serial number: SN-48219."}])
    assert not qa._exact_serial_not_found("Which GPU model did they use?", [])


def test_empty_generation_gets_one_cited_retry(monkeypatch):
    import papertrail.qa as qa

    outputs = iter([
        {"claims": [], "_usage": {"prompt_eval_count": 10}},
        {"claims": [{"text": "The method uses calibration.", "evidence_ids": [0]}],
         "_usage": {"prompt_eval_count": 12}},
        {"results": [{"claim_id": 0, "supported": True, "relevant": True}],
         "coverage_complete": True, "coverage_requirements": ["calibration"], "coverage_gaps": [],
         "_usage": {"prompt_eval_count": 14}},
    ])
    monkeypatch.setattr(qa, "chat_json", lambda *_args, **_kwargs: next(outputs))
    result = qa._synthesize_local("What does the method use?", [{
        "quote": "The method uses calibration to assess uncertainty.",
        "title": "Paper", "pdf_page": 1}], "test-model")
    assert result["generation_retry_used"] is True
    assert result["claims"][0]["support"] == "supported"
    assert result["usage"]["prompt_eval_count"] == 36


def test_complex_synthesis_requires_supported_claim_for_each_subquestion(monkeypatch):
    import json
    import papertrail.qa as qa

    outputs = iter([
        {"claims": [{"text": "Paper A uses method X.", "evidence_ids": [0],
                     "subquestion_ids": [0]}]},
        {"results": [{"claim_id": 0, "supported": True, "relevant": True}],
         "coverage_requirements": ["Paper A method", "Paper B method"],
         "covered_subquestions": [0, 1], "coverage_complete": True, "coverage_gaps": []},
    ])
    monkeypatch.setattr(qa, "chat_json", lambda *_args, **_kwargs: next(outputs))
    result = qa._synthesize_local("Compare Papers A and B.", [{
        "quote": "Paper A uses method X to synthesize tabular data.",
        "title": "Paper A", "pdf_page": 1, "subquestion_ids": [0]}],
        "test-model", ["What does Paper A use?", "What does Paper B use?"])
    assert result["claims"][0]["subquestion_ids"] == [0]
    assert result["coverage_complete"] is False
    assert any("子问题 2 未覆盖" in gap for gap in result["coverage_gaps"])


def test_complex_ask_retrieves_each_subquestion_and_keeps_partial_answer(tmp_path, monkeypatch):
    import papertrail.qa as qa
    from papertrail.retrieval import retrieve as real_retrieve

    db, _ = _indexed_db(tmp_path)
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "complex-test")
    queries = []
    def plan(_question, _model):
        return {"subquestions": ["What method does Paper A use?", "What result does Paper B report?"],
                "usage": {}}
    def tracked_retrieve(database, query, *args, **kwargs):
        queries.append(query)
        return real_retrieve(database, "What does CTGAN evaluate?", *args, **kwargs)
    monkeypatch.setattr(qa, "_plan_subquestions", plan)
    monkeypatch.setattr(qa, "retrieve", tracked_retrieve)
    monkeypatch.setattr(qa, "_screen_evidence", lambda _question, rows, _model: {
        "relevant_ids": [0], "targeted_query": "", "sufficient": True, "usage": {},
    })
    monkeypatch.setattr(qa, "_sentences", lambda _text: [
        "CTGAN evaluates mixed continuous and discrete columns with reliable likelihood and utility measurements."])
    monkeypatch.setattr(qa, "_validate_quote", lambda *_args: True)
    monkeypatch.setattr(qa, "_synthesize_local", lambda *_args: {
        "claims": [{"text": "Paper A uses CTGAN.", "evidence_ids": [0], "subquestion_ids": [0],
                    "support": "supported", "relevant": True, "support_method": "test_judge"}],
        "coverage_complete": False, "coverage_requirements": ["Paper A method", "Paper B result"],
        "coverage_gaps": ["Paper B evidence missing"], "generation_retry_used": False, "usage": {},
    })
    result = qa.ask(db, "Compare Papers A and B.", mode="bm25")
    assert queries == ["What method does Paper A use?", "What result does Paper B report?"]
    assert result["status"] == "generated_partial"
    assert result["claims"][0]["subquestion_ids"] == [0]


def test_qa_preserves_supported_partial_answer_and_logs_reason(tmp_path, monkeypatch):
    import papertrail.qa as qa

    db, _ = _indexed_db(tmp_path)
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "partial-test")
    monkeypatch.setattr(qa, "_screen_evidence", lambda *_args: {
        "relevant_ids": [0], "targeted_query": "", "sufficient": True,
        "selected_chunk_ids": set(), "usage": {},
    })
    monkeypatch.setattr(qa, "_sentences", lambda _text: [
        "CTGAN evaluates mixed continuous and discrete columns with reliable likelihood and utility measurements."])
    monkeypatch.setattr(qa, "_validate_quote", lambda *_args: True)
    monkeypatch.setattr(qa, "_synthesize_local", lambda _question, evidence, _model: {
        "claims": [{"text": "CTGAN evaluates utility.", "evidence_ids": [0],
                    "support": "supported", "relevant": True,
                    "support_method": "test_judge"},
                   {"text": "Unsupported claim.", "evidence_ids": [0],
                    "support": "unsupported", "relevant": True,
                    "support_method": "test_judge"}],
        "coverage_complete": False, "coverage_requirements": ["required detail"],
        "coverage_gaps": ["missing detail"], "usage": {},
    })
    result = qa.ask(db, "What does CTGAN evaluate?", mode="bm25")
    assert result["status"] == "generated_partial", result
    assert result["claims"][0]["text"] == "CTGAN evaluates utility."
    assert "部分回答" in result["answer"]
    assert result["usage"]["_diagnostics"]["refusal_stage"] == "coverage_partial"
    assert result["usage"]["_diagnostics"]["reviewed_claims"] == 2
    assert result["usage"]["_diagnostics"]["rejected_claims"] == 1


def test_qa_runs_one_focused_retrieval_when_screen_finds_gap(tmp_path, monkeypatch):
    import papertrail.qa as qa
    from papertrail.retrieval import retrieve as real_retrieve

    db, _ = _indexed_db(tmp_path)
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "screen-test")
    queries = []
    def tracked_retrieve(database, query, *args, **kwargs):
        queries.append(query)
        return real_retrieve(database, query, *args, **kwargs)
    monkeypatch.setattr(qa, "retrieve", tracked_retrieve)
    screens = iter([
        {"relevant_ids": [0], "targeted_query": "continuous and discrete columns",
         "sufficient": False, "usage": {}},
        {"relevant_ids": [0], "targeted_query": "", "sufficient": True, "usage": {}},
    ])
    monkeypatch.setattr(qa, "_screen_evidence", lambda *_args: next(screens))
    monkeypatch.setattr(qa, "_synthesize_local", lambda _question, _evidence, _model: {
        "claims": [{"text": "CTGAN evaluates utility.", "evidence_ids": [0],
                    "support": "supported", "relevant": True,
                    "support_method": "test_judge"}],
        "coverage_complete": True, "usage": {},
    })
    result = ask(db, "What does CTGAN evaluate?", mode="bm25")
    assert len(queries) == 2
    assert "continuous and discrete columns" in queries[1]
    assert result["status"] == "generated_claims_reviewed"


def test_qa_keeps_initial_evidence_when_focused_search_returns_nothing(tmp_path, monkeypatch):
    import papertrail.qa as qa
    from papertrail.retrieval import retrieve as real_retrieve

    db, _ = _indexed_db(tmp_path)
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "screen-fallback-test")
    calls = 0

    def retrieve_once(database, query, *args, **kwargs):
        nonlocal calls
        calls += 1
        return real_retrieve(database, "What does CTGAN evaluate?", *args, **kwargs) if calls == 1 else []

    monkeypatch.setattr(qa, "retrieve", retrieve_once)
    monkeypatch.setattr(qa, "_screen_evidence", lambda *_args: {
        "relevant_ids": [0], "targeted_query": "missing phrase", "sufficient": False, "usage": {},
    })
    monkeypatch.setattr(qa, "_validate_quote", lambda *_args: True)
    monkeypatch.setattr(qa, "_synthesize_local", lambda _question, evidence, _model: {
        "claims": [{"text": "CTGAN evaluates utility.", "evidence_ids": [0],
                    "support": "supported", "relevant": True, "support_method": "test_judge"}],
        "coverage_complete": True, "usage": {},
    })

    result = qa.ask(db, "What does CTGAN evaluate?", mode="bm25")

    assert calls == 2
    assert result["status"] == "generated_claims_reviewed", result


def test_qa_conversations_do_not_share_follow_up_memory(tmp_path):
    db, _ = _indexed_db(tmp_path)
    first = ask(db, "What does CTGAN evaluate?", conversation_id="conversation-one")
    separate = ask(db, "And its columns?", conversation_id="conversation-two")
    assert first["context_query"] is None
    assert separate["context_query"] is None
