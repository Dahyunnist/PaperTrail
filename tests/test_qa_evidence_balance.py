import papertrail.qa as qa
from papertrail.s1_index import open_database


def test_model_enabled_path_keeps_sentence_quotes_and_standard_candidate_depth(
        tmp_path, monkeypatch):
    database = tmp_path / "mock-model.sqlite3"
    open_database(database).close()
    question = "Compare Alpha and Beta findings across papers."
    subquestions = ["What does Alpha report?", "What does Beta report?"]
    rows_by_query = {
        subquestions[0]: [{
            "chunk_id": "alpha", "version_id": "v-alpha", "paper_id": "alpha-paper",
            "sha256": "a" * 64, "source_type": "original_pdf", "title": "Alpha Study",
            "pdf_page": 1, "path": "alpha.pdf", "text_origin": "native_text",
            "rank_score": 1.0,
            "text": ("Alpha finding is supported by synthetic evidence. "
                     "A neighbor sentence records an unrelated marker."),
        }],
        subquestions[1]: [{
            "chunk_id": "beta", "version_id": "v-beta", "paper_id": "beta-paper",
            "sha256": "b" * 64, "source_type": "original_pdf", "title": "Beta Study",
            "pdf_page": 1, "path": "beta.pdf", "text_origin": "native_text",
            "rank_score": 0.9,
            "text": "Beta finding is supported by synthetic evidence.",
        }],
    }
    retrieval_calls = []
    synthesis_inputs = {}

    monkeypatch.setattr(qa, "configured_model", lambda: "mock-model")
    monkeypatch.setattr(qa, "_requires_decomposition", lambda _question: True)
    monkeypatch.setattr(qa, "_plan_subquestions", lambda *_args: {
        "subquestions": subquestions, "usage": {},
    })

    def retrieve(_database, query, limit, **kwargs):
        retrieval_calls.append((limit, kwargs.get("mode")))
        return rows_by_query[query]

    monkeypatch.setattr(qa, "retrieve", retrieve)
    monkeypatch.setattr(qa, "_screen_evidence", lambda _question, candidates, _model: {
        "relevant_ids": list(range(len(candidates))), "targeted_query": "",
        "sufficient": True, "usage": {},
    })
    monkeypatch.setattr(qa, "_validate_quote", lambda *_args: True)

    def synthesize(_question, evidence, _model, _subquestions):
        synthesis_inputs["quotes"] = [item["quote"] for item in evidence]
        return {
            "claims": [
                {"text": "Alpha synthetic finding.", "evidence_ids": [0], "subquestion_ids": [0],
                 "support": "supported", "relevant": True,
                 "evidence_mapping_valid": True, "support_method": "mock"},
                {"text": "Beta synthetic finding.", "evidence_ids": [1], "subquestion_ids": [1],
                 "support": "supported", "relevant": True,
                 "evidence_mapping_valid": True, "support_method": "mock"},
            ],
            "coverage_complete": True, "covered_subquestions": [0, 1],
            "coverage_requirements": subquestions, "coverage_gaps": [],
            "generation_retry_used": False, "usage": {},
        }

    monkeypatch.setattr(qa, "_synthesize_local", synthesize)

    result = qa.ask(database, question, limit=5, mode="bm25", generate=True)

    assert result["status"] == "generated_claims_reviewed"
    assert retrieval_calls == [(20, "bm25_expanded"), (20, "bm25_expanded")]
    assert "Alpha finding is supported by synthetic evidence." in synthesis_inputs["quotes"]
    assert all(not ("Alpha finding" in quote and "unrelated marker" in quote)
               for quote in synthesis_inputs["quotes"])
