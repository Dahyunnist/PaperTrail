import json
from pathlib import Path

from papertrail.run_manifest import validate_manifest, validate_trace_event

ROOT = Path(__file__).resolve().parents[1]


def _manifest():
    return {"schema_version": 1, "run_id": "synthetic-run", "trace_id": "trace-1",
            "git_sha": "1234567", "dataset_sha256": "a" * 64, "prompt_sha256": None,
            "scorer_sha256": "b" * 64, "split": "synthetic-fixture",
            "runtime": {"python": "CPython 3.12", "platform": "Windows", "lock_sha256": "c" * 64},
            "model_id": None, "gold_source": "synthetic_fixture",
            "budget": {"cap_usd": None, "spent_usd": None, "status": "not_applicable"},
            "cost_usd": None, "status": "passed", "started_at": "2026-11-12T00:00:00Z",
            "completed_at": "2026-11-12T00:00:01Z"}


def test_shared_synthetic_manifests_and_traces_validate():
    manifests = [json.loads(line) for line in (ROOT / "evals/synthetic-run-manifests-v1.jsonl").read_text().splitlines()]
    traces = [json.loads(line) for line in (ROOT / "evals/synthetic-run-traces-v1.jsonl").read_text().splitlines()]
    assert len(manifests) == 2
    assert all(validate_manifest(row) == [] for row in manifests)
    assert all(validate_trace_event(row) == [] for row in traces)


def test_manifest_rejects_missing_provenance_and_non_synthetic_values():
    row = _manifest()
    del row["scorer_sha256"]
    row["gold_source"] = "private_pdf"
    row["model_id"] = "remote-model"
    row["cost_usd"] = 0.1
    issues = validate_manifest(row)
    assert "missing:scorer_sha256" in issues
    assert "synthetic run must declare gold_source=synthetic_fixture" in issues
    assert "offline run must declare model_id=null" in issues
    assert "offline run cost_usd must be null" in issues


def test_manifest_and_trace_reject_secrets_paths_prompts_and_text():
    manifest = _manifest() | {"private_path": "C:\\Users\\person\\paper.pdf", "api_key": "secret"}
    assert any(issue.startswith("forbidden_field") for issue in validate_manifest(manifest))
    event = {"run_id": "r", "trace_id": "t", "span_id": "s", "event_name": "eval.case_completed",
             "timestamp": "2026-11-12T00:00:00Z", "attributes": {"raw_prompt": "question", "full_text": "paper"}}
    assert len([issue for issue in validate_trace_event(event) if issue.startswith("forbidden_field")]) == 2


def test_trace_requires_standard_ids_and_event_name():
    issues = validate_trace_event({"run_id": "r", "trace_id": "t", "event_name": "custom"})
    assert "missing:span_id" in issues
    assert "missing:timestamp" in issues
    assert "invalid:event_name" in issues
