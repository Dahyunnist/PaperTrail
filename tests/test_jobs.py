from pathlib import Path

import pytest

import papertrail.jobs as jobs


class _StopWorker(Exception):
    pass


class _StopWhenIdle:
    def clear(self):
        pass

    def set(self):
        pass

    def wait(self):
        raise _StopWorker


def test_recovered_upload_job_keeps_retry_inputs_until_terminal_state(tmp_path, monkeypatch):
    database = tmp_path / "library.sqlite3"
    sources = tmp_path / "sources.yaml"
    selection = tmp_path / "selection.jsonl"
    sources.write_text("synthetic sources", encoding="utf-8")
    selection.write_text("synthetic selection", encoding="utf-8")
    monkeypatch.setattr(jobs, "_wake", lambda _database: None)
    job_id = jobs.enqueue_index(database, sources, selection, upload_id="upload-1")
    with jobs._connect(database) as conn:
        conn.execute("UPDATE index_jobs SET state='running',attempts=1 WHERE job_id=?", (job_id,))
        conn.execute("CREATE TABLE uploads(upload_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL)")
        conn.execute("INSERT INTO uploads VALUES('upload-1',?)", ("a" * 64,))

    attempts = []

    def index_selection(_database, received_sources, received_selection, **_kwargs):
        attempts.append((Path(received_sources).is_file(), Path(received_selection).is_file()))
        assert attempts[-1] == (True, True)
        if len(attempts) == 1:
            raise RuntimeError("synthetic transient failure")
        return {"issues": []}

    import papertrail.s1_index as indexer
    import papertrail.workspace as workspace
    monkeypatch.setattr(indexer, "index_selection", index_selection)
    monkeypatch.setattr(indexer, "inspect_document", lambda *_args: {"version_id": "version-1"})
    upload_updates = []
    monkeypatch.setattr(workspace, "update_upload",
                        lambda *_args: upload_updates.append(_args[2:]))

    with pytest.raises(_StopWorker):
        jobs._run(database, _StopWhenIdle())

    job = jobs.get_job(database, job_id)
    assert job["state"] == "succeeded"
    assert attempts == [(True, True), (True, True)]
    assert upload_updates and upload_updates[-1][0] == "indexed"
    assert not sources.exists()
    assert not selection.exists()
