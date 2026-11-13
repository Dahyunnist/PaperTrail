import hashlib
import json

import fitz
import pytest

from papertrail.evaluate_run import main, run_evaluation
from papertrail.s1_index import index_selection


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    pdf = root / "synthetic.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "Synthetic evidence anchor proves retrieval.")
    doc.save(pdf)
    doc.close()
    sources = tmp_path / "sources.yaml"
    sources.write_text(f"roots:\n  - id: synthetic\n    path: {root.as_posix()}\n", encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({
        "root_id": "synthetic", "file_name": pdf.name, "relative_path": pdf.name,
        "sha256": _sha(pdf), "kind": "pdf", "source_type": "original_pdf",
    }) + "\n", encoding="utf-8")
    database = tmp_path / "index.sqlite3"
    index_selection(database, sources, selection)
    gold = tmp_path / "gold.jsonl"
    gold_rows = [
        {"id": "SYN-1", "question_type": "fact_location", "question": "synthetic evidence anchor",
         "expected_answer": "retrieval", "abstain": False, "evidence": [{
             "root_id": "synthetic", "file_name": pdf.name, "sha256": _sha(pdf),
             "pdf_page": 1, "quote": "Synthetic evidence anchor proves retrieval."}]},
        {"id": "SYN-2", "question_type": "unanswerable", "question": "missing fact",
         "expected_answer": "unknown", "abstain": True, "evidence": []},
    ]
    gold.write_text("".join(json.dumps(row) + "\n" for row in gold_rows), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "dataset_id": "synthetic-fixture-test", "source_type": "synthetic_only",
        "gold_file": gold.name, "gold_sha256": _sha(gold), "question_count": len(gold_rows),
        "limits": ["Synthetic fixture only; not a real-paper benchmark."],
    }), encoding="utf-8")
    return database, gold, manifest


def test_manifest_bound_evaluation_separates_runtime(tmp_path):
    database, gold, manifest = _fixture(tmp_path)
    report_path = tmp_path / "reports" / "result.json"
    report = run_evaluation(database, gold, manifest, report_path,
                            k=1, modes=("bm25",), minimum_questions=1)
    assert report["dataset"]["source_type"] == "synthetic_only"
    assert report["provenance"]["gold_sha256"] == _sha(gold)
    assert report["provenance"]["source_manifest_sha256"] == _sha(manifest)
    assert "mean_query_ms" not in report["evaluation"]["modes"]["bm25"]
    assert "mean_query_ms" in report["runtime"]["query_latency_by_mode"]["bm25"]
    assert report["evaluation"]["answerable_questions"] == 1
    assert report["evaluation"]["unanswerable_questions"] == 1
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_manifest_bound_evaluation_rejects_changed_gold_hash(tmp_path):
    database, gold, manifest = _fixture(tmp_path)
    gold.write_text(gold.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gold SHA-256"):
        run_evaluation(database, gold, manifest, tmp_path / "out.json",
                       k=1, modes=("bm25",), minimum_questions=1)
    assert not (tmp_path / "out.json").exists()


def test_manifest_bound_evaluation_rejects_question_count_mismatch(tmp_path):
    database, gold, manifest = _fixture(tmp_path)
    row = json.loads(manifest.read_text(encoding="utf-8"))
    row["question_count"] = 99
    manifest.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="question_count"):
        run_evaluation(database, gold, manifest, tmp_path / "out.json",
                       k=1, modes=("bm25",), minimum_questions=1)
    assert not (tmp_path / "out.json").exists()


def test_cli_emits_report_for_synthetic_fixture(tmp_path, monkeypatch, capsys):
    import sys

    database, gold, manifest = _fixture(tmp_path)
    output = tmp_path / "cli.json"
    monkeypatch.setattr(sys, "argv", ["evaluate_run", "--db", str(database),
                                      "--gold", str(gold), "--manifest", str(manifest),
                                      "--report", str(output), "--k", "1",
                                      "--minimum-questions", "1", "--modes", "bm25"])
    main()
    assert "questions=1" in capsys.readouterr().out
    assert output.is_file()
