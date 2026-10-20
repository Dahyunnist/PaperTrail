import hashlib
import json
from pathlib import Path

import fitz
import yaml

import papertrail.qa as qa
from papertrail.evaluate_qa import compare_qa
from papertrail.s1_index import index_selection


def test_qa_evaluation_compares_extractive_and_reviewed_modes(tmp_path, monkeypatch):
    root = tmp_path / "papers"
    root.mkdir()
    source = root / "paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "Anchorword Research", fontsize=16)
    page.insert_text((40, 100), "Anchorword evidence supports the measured research result on this page.")
    doc.save(source)
    doc.close()
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "papers", "path": str(root)}]}), encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({"root_id": "papers", "file_name": source.name,
        "relative_path": source.name, "sha256": sha, "kind": "pdf", "source_type": "original_pdf"}) + "\n",
        encoding="utf-8")
    db = tmp_path / "library.sqlite3"
    index_selection(db, config, selection)
    item = {"id": "T-1", "question_type": "fact_location", "question": "Anchorword evidence?",
            "expected_answer": "measured research result", "abstain": False,
            "evidence": [{"sha256": sha, "pdf_page": 1}]}
    monkeypatch.setattr("papertrail.evaluate_qa.load_gold", lambda _path: [item])
    monkeypatch.setenv("PAPERTRAIL_LLM_MODEL", "fake-model")
    monkeypatch.setattr(qa, "_synthesize_local", lambda _question, _evidence, _model: {
        "claims": [{"text": "The result is measured.", "evidence_ids": [0],
                    "support": "supported", "support_method": "local_llm_judge"}], "usage": {"eval_count": 5}})
    result = compare_qa(db, tmp_path / "gold.jsonl", tmp_path / "result.json", "bm25")
    assert result["extractive"]["questions"] == 1
    assert result["model_reviewed"]["by_question_type"]["fact_location"]["total"] == 1
    assert result["model_reviewed"]["completion_tokens"] == 5
