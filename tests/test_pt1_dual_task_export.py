import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import export_pt1_dual_annotation_tasks as exporter


TASK_FIELDS = ["task_id", "paper_split", "doi", "title", "pdf_sha256", "candidate_type",
    "candidate_question", "candidate_basis", "candidate_basis_pdf_page", "question_type",
    "answerability", "expected_answer", "minimal_complete_evidence_quote", "evidence_pdf_pages",
    "original_pdf_excerpt", "span_start_char", "span_end_char", "annotator", "reviewer",
    "review_status", "notes"]


def _inputs(tmp_path, papers=30):
    manifest_sources = []
    task_rows = []
    for index in range(papers):
        doi = f"10.9999/synthetic-{index:02}"
        digest = f"{index + 1:064x}"
        source = {"doi": doi, "title": f"Synthetic Paper {index}", "year": 2026,
            "source_version": "synthetic-fixture-v1", "public_record": f"https://example.test/{index}",
            "download_url": f"https://example.test/{index}.pdf", "license": "CC BY 4.0",
            "license_statement": "Synthetic license record.", "license_evidence": f"https://example.test/{index}/license",
            "license_policy": "https://example.test/policy", "license_version_url": "https://creativecommons.org/licenses/by/4.0/",
            "pdf_sha256": digest, "paper_split": "development_seen", "local_pdf": f"private/{index}.pdf"}
        manifest_sources.append(source)
        task_count = 2 if index < 40 - papers else 1
        for task_index in range(task_count):
            number = len(task_rows) + 1
            task_rows.append({"task_id": f"PT1-H{number:03}", "paper_split": "development_seen",
                "doi": doi, "title": source["title"], "pdf_sha256": digest,
                "candidate_type": "synthetic candidate", "candidate_question": f"Synthetic question {number}?",
                "candidate_basis": "Synthetic heading", "candidate_basis_pdf_page": "1",
                **{field: "" for field in TASK_FIELDS if field not in {"task_id", "paper_split", "doi", "title", "pdf_sha256", "candidate_type", "candidate_question", "candidate_basis", "candidate_basis_pdf_page"}}})
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"dataset_id": "synthetic-dataset", "frozen_at": "2026-11-12",
        "source_count": papers, "sources": manifest_sources}), encoding="utf-8")
    tasks_path = tmp_path / "tasks.csv"
    with tasks_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TASK_FIELDS)
        writer.writeheader()
        writer.writerows(task_rows)
    return tasks_path, manifest_path, task_rows, manifest_sources


def test_export_has_two_fillable_copies_and_grouped_license_provenance(tmp_path):
    tasks, manifest, _, _ = _inputs(tmp_path)
    outputs = exporter.export(tasks, manifest, tmp_path / "out", "synthetic-40")
    frozen = json.loads(outputs["frozen"].read_text(encoding="utf-8"))
    assert frozen["question_count"] == 40
    assert frozen["paper_count"] == 30
    assert len(frozen["source_groups"]) == 30
    assert exporter.validate_frozen(outputs["frozen"], tasks, manifest) == []
    for key in ("annotator_a", "annotator_b"):
        with outputs[key].open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 40
        assert all(row["license"] == "CC BY 4.0" and row["license_evidence"] for row in rows)
        assert all(not row["annotator_id"] and not row["independent"] and not row["answerability"]
                   and not row["expected_answer"] and not row["evidence"] and not row["question_type"]
                   for row in rows)
        serialized = outputs[key].read_text(encoding="utf-8-sig")
        assert "private/" not in serialized and "local_pdf" not in serialized


def test_export_rejects_out_of_plan_paper_coverage(tmp_path):
    tasks, manifest, _, _ = _inputs(tmp_path, papers=29)
    with pytest.raises(ValueError, match="30-60 distinct papers"):
        exporter.build(tasks, manifest)


def test_export_rejects_missing_license_evidence_record(tmp_path):
    tasks, manifest, _, sources = _inputs(tmp_path)
    sources[0]["license_evidence"] = ""
    manifest.write_text(json.dumps({"dataset_id": "synthetic-dataset", "frozen_at": "2026-11-12",
        "source_count": len(sources), "sources": sources}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing public provenance fields: license_evidence"):
        exporter.build(tasks, manifest)


def test_frozen_input_hashes_ignore_windows_line_ending_conversion(tmp_path):
    tasks, manifest, _, _ = _inputs(tmp_path)
    windows_copy = tmp_path / "tasks-windows.csv"
    canonical = tasks.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    windows_copy.write_bytes(canonical.replace(b"\n", b"\r\n"))
    assert exporter._sha256(tasks) == exporter._sha256(windows_copy)


def test_frozen_grouped_list_detects_source_record_tampering(tmp_path):
    tasks, manifest, _, _ = _inputs(tmp_path)
    outputs = exporter.export(tasks, manifest, tmp_path / "out", "synthetic-40")
    frozen = json.loads(outputs["frozen"].read_text(encoding="utf-8"))
    frozen["source_groups"][0]["license"] = "Unknown"
    outputs["frozen"].write_text(json.dumps(frozen), encoding="utf-8")
    issues = exporter.validate_frozen(outputs["frozen"], tasks, manifest)
    assert issues == ["frozen grouped list does not match task CSV and source manifest"]


def test_existing_anonymous_package_covers_40_tasks_and_30_sources():
    package = json.loads((ROOT / "evals/pt1-human-annotation-package-40-20261112.json").read_text(encoding="utf-8"))
    assert len(package["tasks"]) == 40
    assert len({row["source_id"] for row in package["tasks"]}) == 30
    assert package["gold_status"] == "pending_human_annotation"


def test_checked_in_exports_are_blank_paired_and_frozen_by_source():
    prefix = "pt1-dual-annotation-40-20261112"
    frozen_path = ROOT / "evals" / f"{prefix}-frozen-grouped.json"
    tasks_path = ROOT / "evals/pt1-human-annotation-task-40-20261111.csv"
    manifest_path = ROOT / "evals/pt1-candidate-manifest-20261111.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    frozen_text = frozen_path.read_text(encoding="utf-8")
    assert exporter.validate_frozen(frozen_path, tasks_path, manifest_path) == []
    assert frozen["question_count"] == 40 and frozen["paper_count"] == 30
    assert all(len(group["task_ids"]) >= 1 for group in frozen["source_groups"])
    assert "local_pdf" not in frozen_text and "private/" not in frozen_text
    assert sum(not group["source_version"] for group in frozen["source_groups"]) == 3
    for slot in ("a", "b"):
        with (ROOT / "evals" / f"{prefix}-{slot}.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 40
        assert {row["annotation_slot"] for row in rows} == {slot.upper()}
        assert all(not row["annotator_id"] and not row["independent"] and not row["answerability"]
                   and not row["expected_answer"] and not row["evidence"] for row in rows)
        assert all(row["license"] and row["license_evidence"] and row["public_record"] for row in rows)
        assert "local_pdf" not in (ROOT / "evals" / f"{prefix}-{slot}.csv").read_text(encoding="utf-8-sig")
