import pytest

from papertrail.shared_manifest import to_shared_manifest, validate_shared_manifest


def _pt_manifest():
    return {
        "git_sha": "a" * 40, "dataset_id": "fixture", "dataset_sha256": "b" * 64,
        "split": "development", "model_id": "none", "prompt_sha256": None,
        "scorer_sha256": "c" * 64, "gold_source": "synthetic_fixture",
        "cost_usd": 0, "run_id": "run-1", "trace_id": "trace-1",
        "started_at": "2026-11-13T00:00:00+00:00", "completed_at": "2026-11-13T00:01:00+00:00",
        "status": "passed", "runtime": {"python": "3.x", "platform": "test",
                                            "lock_sha256": "d" * 64},
        "budget": {"cap_usd": None, "spent_usd": 0, "status": "not_applicable"},
    }


def test_shared_manifest_maps_existing_metadata_and_nulls_absent_fields():
    shared = to_shared_manifest(_pt_manifest())
    assert shared["model_id"] == "none"
    assert shared["gold_source"] == "synthetic_fixture"
    assert shared["cost_usd_estimate"] == 0
    assert shared["run_id"] == "run-1" and shared["trace_id"] == "trace-1"
    assert shared["tool_schema_sha"] is None and shared["max_steps"] is None
    assert shared["span_id"] is None
    assert shared["runtime_digest"]


def test_shared_manifest_rejects_private_fields():
    manifest = _pt_manifest()
    manifest["absolute_path"] = "E:/private/paper.pdf"
    with pytest.raises(ValueError, match="private field rejected"):
        to_shared_manifest(manifest)


@pytest.mark.parametrize("change, message", [
    ({"dataset_sha256": "bad"}, "dataset_sha256 invalid"),
    ({"ended_at": "2026-11-12T00:00:00+00:00"}, "timestamp order invalid"),
    ({"cost_usd": -1}, "cost_usd_estimate invalid"),
    ({"split": "E:/private/set"}, "private path value rejected"),
])
def test_shared_manifest_rejects_bad_values(change, message):
    source = _pt_manifest()
    source.update(change)
    with pytest.raises(ValueError, match=message):
        to_shared_manifest(source)


def test_shared_manifest_validator_rejects_path_in_value():
    shared = to_shared_manifest(_pt_manifest())
    shared["dataset_id"] = "/home/user/private"
    with pytest.raises(ValueError, match="private path value rejected"):
        validate_shared_manifest(shared)
