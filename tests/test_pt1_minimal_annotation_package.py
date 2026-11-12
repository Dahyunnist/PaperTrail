import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_builder_uses_metadata_only_and_leaves_gold_blank():
    builder = _load("pt1_package_builder", "scripts/build_pt1_minimal_annotation_package.py")
    package = builder.build(ROOT / "evals/pt1-human-annotation-task-5-20261111.csv",
                            ROOT / "evals/pt1-candidate-manifest-20261111.json")
    assert len(package["tasks"]) == 5
    for task in package["tasks"]:
        assert len(task["pdf_sha256"]) == 64
        assert task["source_id"] == "pt1pdf-" + task["pdf_sha256"][:16]
        assert set(task) == {"task_id", "source_id", "pdf_sha256", "question", "human_fields"}
        assert all(value is None for value in task["human_fields"].values())


def test_package_validator_rejects_filled_gold_and_private_fields(tmp_path):
    builder = _load("pt1_package_builder", "scripts/build_pt1_minimal_annotation_package.py")
    validator = _load("pt1_package_validator", "scripts/validate_pt1_minimal_annotation_package.py")
    package = builder.build(ROOT / "evals/pt1-human-annotation-task-5-20261111.csv",
                            ROOT / "evals/pt1-candidate-manifest-20261111.json")
    path = tmp_path / "package.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    assert validator.validate(path) == []
    package["tasks"][0]["human_fields"]["expected_answer"] = "fabricated"
    package["tasks"][0]["local_pdf"] = "C:/private/paper.pdf"
    path.write_text(json.dumps(package), encoding="utf-8")
    issues = validator.validate(path)
    assert any("gold field must remain blank" in issue for issue in issues)
    assert any("unexpected or missing top-level fields" in issue for issue in issues)
