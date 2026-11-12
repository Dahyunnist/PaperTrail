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


def test_trace_writer_does_nothing_without_explicit_path(tmp_path, monkeypatch):
    monkeypatch.delenv("PAPERTRAIL_TRACE_JSONL", raising=False)
    trace.emit("human.reviewed", label="supports")
    assert list(tmp_path.iterdir()) == []
