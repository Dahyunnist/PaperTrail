import hashlib
import json
from copy import deepcopy

import fitz
import pytest

import papertrail.evaluate_run as evaluate_run_module
from papertrail.evaluate_run import main, run_evaluation, validate_run_manifest
from papertrail.s1_index import index_selection
from papertrail.run_manifest import validate_trace_event


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
        "dataset_id": "synthetic-fixture-test", "split": "test", "source_type": "synthetic_only",
        "gold_source": "synthetic_fixture",
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
    run_manifest = report["run_manifest"]
    assert run_manifest["project"] == "PaperTrail"
    assert run_manifest["model_id"] == "none"
    assert run_manifest["gold_source"] == "synthetic_fixture"
    assert run_manifest["cost_usd_estimate"] == 0
    assert run_manifest["usage"] == {
        "request_count": 0, "response_count": 0, "cost_usd_estimate": 0,
        "status": "observed_zero_requests",
    }
    assert report["shared_manifest_v2"]["usage"] == run_manifest["usage"]
    assert report["shared_manifest_v2"]["field_status"]["usage"] == "recorded"
    assert run_manifest["scorer_sha"] == _sha(
        evaluate_run_module.Path(__file__).resolve().parents[1] / "papertrail" / "evaluate.py"
    )
    assert run_manifest["max_steps"] is None
    assert report["shared_manifest"]["field_status"]["max_steps"] == "not_applicable"
    assert run_manifest["question_count"] == 2
    assert run_manifest["report_fingerprint"]
    assert report["shared_manifest"]["status"] == "passed"
    assert report["shared_manifest"]["span_id"] is None
    assert report["shared_manifest"]["field_status"]["span_id"] == "not_recorded"
    expected_dataset_hash = hashlib.sha256(json.dumps({
        "source_manifest_sha256": _sha(manifest), "gold_sha256": _sha(gold),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert run_manifest["dataset_sha256"] == expected_dataset_hash
    assert run_manifest["gold_sha256"] == _sha(gold)
    assert run_manifest["source_manifest_sha256"] == _sha(manifest)
    assert "limits" not in report
    validate_run_manifest(run_manifest)
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_run_manifest_rejects_missing_fields_bad_hash_and_false_model_cost(tmp_path):
    database, gold, source_manifest = _fixture(tmp_path)
    report = run_evaluation(database, gold, source_manifest, tmp_path / "run.json",
                            k=1, modes=("bm25",), minimum_questions=1)
    valid = report["run_manifest"]

    missing = deepcopy(valid)
    del missing["trace_id"]
    with pytest.raises(ValueError, match="fields missing"):
        validate_run_manifest(missing)

    bad_hash = deepcopy(valid)
    bad_hash["source_manifest_sha256"] = "bad"
    with pytest.raises(ValueError, match="source_manifest_sha256 invalid"):
        validate_run_manifest(bad_hash)

    false_model_cost = deepcopy(valid)
    false_model_cost["cost_usd_estimate"] = 0.01
    with pytest.raises(ValueError, match="cost or status invalid"):
        validate_run_manifest(false_model_cost)

    fabricated_model_metadata = deepcopy(valid)
    fabricated_model_metadata["runtime_digest"] = "a" * 64
    with pytest.raises(ValueError, match="no-model boundary"):
        validate_run_manifest(fabricated_model_metadata)

    contaminated = deepcopy(valid)
    contaminated["raw_prompt"] = "should never be present"
    with pytest.raises(ValueError, match="sensitive field"):
        validate_run_manifest(contaminated)

    alternate_gold_source = deepcopy(valid)
    alternate_gold_source["gold_source"] = "manual_review"
    assert validate_run_manifest(alternate_gold_source) is None

    missing_gold_source = deepcopy(valid)
    missing_gold_source["gold_source"] = ""
    with pytest.raises(ValueError, match="gold_source"):
        validate_run_manifest(missing_gold_source)

    malformed_timestamp = deepcopy(valid)
    malformed_timestamp["started_at"] = "yesterday"
    with pytest.raises(ValueError, match="ISO-8601"):
        validate_run_manifest(malformed_timestamp)

    reversed_timestamp = deepcopy(valid)
    reversed_timestamp["ended_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="timestamp range"):
        validate_run_manifest(reversed_timestamp)


def test_manifest_requires_dataset_identity_before_writing_report(tmp_path):
    database, gold, source_manifest = _fixture(tmp_path)
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    source.pop("dataset_id")
    source_manifest.write_text(json.dumps(source), encoding="utf-8")
    output = tmp_path / "out.json"
    with pytest.raises(ValueError, match="dataset_id"):
        run_evaluation(database, gold, source_manifest, output,
                       k=1, modes=("bm25",), minimum_questions=1)
    assert not output.exists()


def test_missing_gold_source_is_null_and_marked_not_recorded(tmp_path):
    database, gold, source_manifest = _fixture(tmp_path)
    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    source.pop("gold_source")
    source_manifest.write_text(json.dumps(source), encoding="utf-8")
    report = run_evaluation(database, gold, source_manifest, tmp_path / "out.json",
                            k=1, modes=("bm25",), minimum_questions=1)
    assert report["run_manifest"]["gold_source"] is None
    assert report["shared_manifest"]["gold_source"] is None
    assert report["shared_manifest"]["field_status"]["gold_source"] == "not_recorded"


def test_evaluation_report_and_failure_trace_are_safe_and_correlated(tmp_path, monkeypatch):
    database, gold, manifest = _fixture(tmp_path)
    gold_rows = [json.loads(line) for line in gold.read_text(encoding="utf-8").splitlines()]
    gold_rows[0]["question"] = "QUESTION_SENTINEL_PRIVATE"
    gold_rows[0]["expected_answer"] = "ANSWER_SENTINEL_PRIVATE"
    gold.write_text("".join(json.dumps(row) + "\n" for row in gold_rows), encoding="utf-8")
    source = json.loads(manifest.read_text(encoding="utf-8"))
    source["gold_sha256"] = _sha(gold)
    source["limits"] = ["LIMITS_SENTINEL_PRIVATE"]
    manifest.write_text(json.dumps(source), encoding="utf-8")
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("PAPERTRAIL_TRACE_JSONL", str(trace_path))

    def fail_comparison(*args, **kwargs):
        from papertrail.trace import emit
        emit("retrieval.completed", mode="bm25", result_count=0, status="failed")
        raise RuntimeError("FAILURE_SENTINEL_PRIVATE")

    monkeypatch.setattr(evaluate_run_module, "compare_modes", fail_comparison)
    report_path = tmp_path / "failure.json"
    with pytest.raises(RuntimeError, match="FAILURE_SENTINEL_PRIVATE"):
        run_evaluation(database, gold, manifest, report_path,
                       k=1, modes=("bm25",), minimum_questions=1)

    report_text = report_path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["run_manifest"]["status"] == "failed"
    assert report["shared_manifest"]["status"] == "failed"
    assert report["shared_manifest_v2"]["usage"]["status"] == "observed_zero_requests"
    assert report["failure"] == {"stage": "compare_modes", "error_type": "RuntimeError"}
    assert report["run_manifest"]["git_sha"]
    assert report["run_manifest"]["dataset_sha256"]
    assert report["run_manifest"]["scorer_sha"]
    assert report["run_manifest"]["gold_sha256"] == _sha(gold)
    assert report["run_manifest"]["source_manifest_sha256"] == _sha(manifest)
    assert all(secret not in report_text for secret in (
        "QUESTION_SENTINEL_PRIVATE", "ANSWER_SENTINEL_PRIVATE",
        "LIMITS_SENTINEL_PRIVATE", "FAILURE_SENTINEL_PRIVATE"))
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_name"] for event in events] == [
        "retrieval.completed", "evaluation.usage", "evaluation.failed"]
    usage = events[1]
    assert {key: usage[key] for key in (
        "request_count", "response_count", "cost_usd_estimate", "usage_status"
    )} == {
        "request_count": 0, "response_count": 0, "cost_usd_estimate": 0,
        "usage_status": "observed_zero_requests",
    }
    assert all(validate_trace_event(event) == [] for event in events)
    assert all(event["run_id"] == report["run_manifest"]["run_id"] for event in events)
    assert all(event["trace_id"] == report["run_manifest"]["trace_id"] for event in events)
    assert len({event["span_id"] for event in events}) == 3
    assert "FAILURE_SENTINEL_PRIVATE" not in trace_path.read_text(encoding="utf-8")


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


@pytest.mark.parametrize("change, message", [
    ({"gold_file": "other.jsonl"}, "gold_file"),
    ({"source_type": ""}, "source_type"),
])
def test_manifest_rejects_wrong_gold_path_or_missing_source_type(tmp_path, change, message):
    database, gold, manifest = _fixture(tmp_path)
    row = json.loads(manifest.read_text(encoding="utf-8"))
    row.update(change)
    manifest.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        run_evaluation(database, gold, manifest, tmp_path / "out.json",
                       k=1, modes=("bm25",), minimum_questions=1)


def test_manifest_without_question_count_reports_validated_total(tmp_path):
    database, gold, manifest = _fixture(tmp_path)
    row = json.loads(manifest.read_text(encoding="utf-8"))
    del row["question_count"]
    manifest.write_text(json.dumps(row), encoding="utf-8")
    report = run_evaluation(database, gold, manifest, tmp_path / "out.json",
                            k=1, modes=("bm25",), minimum_questions=1)
    assert report["dataset"]["question_count"] == 2
    assert report["evaluation"]["unanswerable_questions"] == 1


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
