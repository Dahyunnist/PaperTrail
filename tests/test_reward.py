import json

import fitz
import yaml

from papertrail.audit import _hash
from papertrail.qa import ask
from papertrail.reward import export_trajectories, rate_trajectory, trajectory_rows
from papertrail.s1_index import index_selection


def _indexed_db(tmp_path):
    root = tmp_path / "papers"
    root.mkdir()
    source = root / "paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "CTGAN Evidence Article", fontsize=16)
    page.insert_text((40, 100), "CTGAN evaluates mixed continuous and discrete columns with reliable utility measurements.")
    doc.save(source)
    doc.close()
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "papers", "path": str(root)}]}), encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({"root_id": "papers", "file_name": source.name,
        "relative_path": source.name, "sha256": _hash(source), "kind": "pdf",
        "source_type": "original_pdf"}) + "\n", encoding="utf-8")
    db = tmp_path / "library.sqlite3"
    index_selection(db, config, selection)
    return db


def test_trajectory_records_evidence_latency_and_human_reward(tmp_path):
    db = _indexed_db(tmp_path)
    result = ask(db, "What does CTGAN evaluate?")
    before = trajectory_rows(db)[0]
    assert before["latency_ms"] > 0
    assert before["retrieval"] and before["evidence_refs"]
    assert all("path" not in item for item in before["evidence_refs"])
    rated = rate_trajectory(db, result["turn_id"], "correct", "逐条对照原文")
    assert rated["reward"] <= 1.0
    assert rated["components"]["human_rating_base"] == 1.0
    out = tmp_path / "trajectories.jsonl"
    assert export_trajectories(db, out) == 1
    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["user_rating"] == "correct"
    assert row["reward"] == rated["reward"]

