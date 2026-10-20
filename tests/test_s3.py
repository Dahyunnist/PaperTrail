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


def test_qa_conversations_do_not_share_follow_up_memory(tmp_path):
    db, _ = _indexed_db(tmp_path)
    first = ask(db, "What does CTGAN evaluate?", conversation_id="conversation-one")
    separate = ask(db, "And its columns?", conversation_id="conversation-two")
    assert first["context_query"] is None
    assert separate["context_query"] is None
