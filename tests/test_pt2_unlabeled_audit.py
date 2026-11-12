import hashlib
import importlib.util
import json
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_pt2_unlabeled_retrieval", ROOT / "scripts/audit_pt2_unlabeled_retrieval.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_unlabeled_audit_rebuilds_synthetic_bm25_and_omits_text(tmp_path):
    source_dir = tmp_path / "synthetic"
    source_dir.mkdir()
    source = source_dir / "only-synthetic.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "Synthetic Audit Study")
    page.insert_text((40, 100), "amber-only-synthetic-marker supports local BM25 retrieval audit.")
    doc.save(source)
    doc.close()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    config = tmp_path / "sources.yaml"
    config.write_text(f"roots:\n  - id: fixture\n    path: {source_dir.as_posix()}\n    kinds: [pdf]\n", encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({"root_id": "fixture", "file_name": source.name,
        "relative_path": source.name, "sha256": digest, "kind": "pdf", "source_type": "original_pdf"}) + "\n",
        encoding="utf-8")
    queries = tmp_path / "queries.jsonl"
    queries.write_text(json.dumps({"id": "Q-SYN-1", "query": "amber-only-synthetic-marker"}) + "\n",
                        encoding="utf-8")
    output = tmp_path / "audit.json"

    report = audit.run(tmp_path / "audit.sqlite3", config, selection, queries, output)
    serialized = output.read_text(encoding="utf-8")
    assert report["run_type"] == "unlabeled_retrieval_audit"
    assert report["gold_metrics"] is None and report["model_id"] is None and report["cost_usd"] is None
    assert report["results"][0]["candidate_count"] > 0
    assert "amber-only-synthetic-marker" not in serialized
    assert str(source_dir) not in serialized
    assert "Synthetic Audit Study" not in serialized
