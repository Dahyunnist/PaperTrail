import pytest
import json
from pathlib import Path

from papertrail.shared_manifest import (to_shared_manifest, to_shared_manifest_v1,
                                        to_shared_manifest_v2, validate_shared_manifest,
                                        validate_shared_manifest_v2)


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
    assert shared["field_status"]["tool_schema_sha"] == "not_applicable"
    assert to_shared_manifest_v1(_pt_manifest()) == shared
    assert shared["project"] == "PaperTrail"
    assert shared["max_steps"] is None
    assert shared["field_status"]["max_steps"] == "not_applicable"


def test_shared_manifest_derives_stable_dataset_identity_when_legacy_input_lacks_id():
    source = _pt_manifest()
    source.pop("dataset_id")
    shared = to_shared_manifest_v1(source)
    assert shared["dataset_id"] == f"sha256:{source['dataset_sha256']}"
    assert shared["field_status"]["span_id"] == "not_recorded"


def test_shared_manifest_schema_matches_projection_contract():
    schema = json.loads((Path(__file__).resolve().parents[1] / "evals/run-manifest-v1.schema.json").read_text(encoding="utf-8"))
    shared = to_shared_manifest(_pt_manifest())
    assert set(schema["required"]) == set(shared)
    assert schema["properties"]["field_status"]["additionalProperties"]["enum"] == [
        "recorded", "not_applicable", "not_recorded", "blocked"]


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


def test_shared_manifest_rejects_null_without_state_and_bad_state():
    shared = to_shared_manifest(_pt_manifest())
    del shared["field_status"]["span_id"]
    with pytest.raises(ValueError, match="null field status missing"):
        validate_shared_manifest(shared)
    shared = to_shared_manifest(_pt_manifest())
    shared["field_status"]["max_steps"] = "available"
    with pytest.raises(ValueError, match="field status invalid"):
        validate_shared_manifest(shared)


def test_shared_manifest_v2_records_observed_zero_usage_and_preserves_unknowns():
    source = _pt_manifest()
    source["usage"] = {"request_count": 0, "response_count": 0,
                       "cost_usd_estimate": 0,
                       "status": "observed_zero_requests"}
    observed = to_shared_manifest_v2(source)
    assert observed["schema_version"] == 2
    assert observed["usage"] == source["usage"]
    assert observed["field_status"]["usage"] == "recorded"
    assert observed["cost_usd_estimate"] == 0
    validate_shared_manifest_v2(observed)

    source.pop("usage")
    source["model_id"] = "historical-model"
    source.pop("cost_usd")
    unknown = to_shared_manifest_v2(source)
    assert unknown["usage"] is None
    assert unknown["field_status"]["usage"] == "not_recorded"
    assert unknown["cost_usd_estimate"] is None
    assert unknown["field_status"]["cost_usd_estimate"] == "not_recorded"
    validate_shared_manifest_v2(unknown)


def test_shared_manifest_v2_rejects_unproven_zero_usage():
    source = _pt_manifest()
    source["usage"] = {"request_count": 0, "response_count": 0,
                       "cost_usd_estimate": 0, "status": "estimated"}
    with pytest.raises(ValueError, match="observed_zero_requests"):
        to_shared_manifest_v2(source)


def test_shared_manifest_v2_schema_matches_projection():
    schema = json.loads((Path(__file__).resolve().parents[1] / "evals/run-manifest-v2.schema.json").read_text(encoding="utf-8"))
    source = _pt_manifest()
    source["usage"] = {"request_count": 0, "response_count": 0,
                       "cost_usd_estimate": 0,
                       "status": "observed_zero_requests"}
    projected = to_shared_manifest_v2(source)
    assert set(schema["required"]) == set(projected)
    assert schema["properties"]["usage"]["anyOf"][1]["properties"]["status"]["const"] == "observed_zero_requests"


@pytest.mark.parametrize("field, value, message", [
    ("git_sha", "bad", "git_sha invalid"),
    ("max_steps", True, "max_steps invalid"),
    ("max_tokens", 0, "max_tokens invalid"),
    ("run_id", " ", "run_id invalid"),
])
def test_shared_manifest_rejects_invalid_common_fields(field, value, message):
    shared = to_shared_manifest(_pt_manifest())
    shared[field] = value
    shared["field_status"][field] = "recorded"
    with pytest.raises(ValueError, match=message):
        validate_shared_manifest(shared)
