import json

from papertrail import trace


def test_jsonl_trace_is_opt_in_and_filters_private_values(tmp_path, monkeypatch):
    target = tmp_path / "trace.jsonl"
    monkeypatch.setenv("PAPERTRAIL_TRACE_JSONL", str(target))
    trace.emit("retrieval.completed", mode="bm25", result_count=2,
               query="private question", path="C:/private/paper.pdf")
    row = json.loads(target.read_text(encoding="utf-8"))
    assert row["event_name"] == "retrieval.completed"
    assert row["mode"] == "bm25"
    assert "query" not in row and "path" not in row
    assert row["run_id"] and row["trace_id"] and row["span_id"]


def test_trace_drops_unknown_and_non_scalar_attributes_without_interrupting(tmp_path, monkeypatch):
    target = tmp_path / "trace.jsonl"
    monkeypatch.setenv("PAPERTRAIL_TRACE_JSONL", str(target))
    trace.emit("retrieval.completed", mode={"query": "private question"},
               result_count=2, query="private question", path="C:/private/paper.pdf")
    row = json.loads(target.read_text(encoding="utf-8"))
    assert row["result_count"] == 2
    assert not {"query", "path", "mode"} & row.keys()
    assert "private question" not in target.read_text(encoding="utf-8")
    assert "C:/private/paper.pdf" not in target.read_text(encoding="utf-8")


def test_trace_writer_does_nothing_without_explicit_path(tmp_path, monkeypatch):
    monkeypatch.delenv("PAPERTRAIL_TRACE_JSONL", raising=False)
    trace.emit("human.reviewed", label="supports")
    assert list(tmp_path.iterdir()) == []


def test_new_lifecycle_events_match_manifest_schema(tmp_path, monkeypatch):
    from papertrail.run_manifest import validate_trace_event

    target = tmp_path / "trace.jsonl"
    monkeypatch.setenv("PAPERTRAIL_TRACE_JSONL", str(target))
    trace.emit("timeout", operation="model_request", provider="ollama", path="private")
    trace.emit("retry", operation="claim_generation", attempt=2)
    trace.emit("budget_exceeded", budget_type="model_calls", limit=16)
    trace.emit("checkpoint_resume", component="index_jobs", resumed_count=1)
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert [row["event_name"] for row in rows] == [
        "timeout", "retry", "budget_exceeded", "checkpoint_resume"]
    assert all(validate_trace_event(row) == [] for row in rows)
    assert all("path" not in row for row in rows)
