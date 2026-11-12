import ast
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate_pt2_synthetic", ROOT / "scripts/evaluate_pt2_synthetic.py")
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


def test_frozen_synthetic_fixture_has_full_evidence_coverage(tmp_path):
    result_path = tmp_path / "results.jsonl"
    result = evaluate.run(tmp_path / "fixture", result_path)
    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
    assert result["fixture_version"] == "pt2-synthetic-evidence-v1"
    assert len(result["pdf_sha256"]) == 3
    assert len(rows) == 9
    assert {row["method"] for row in rows} == {"bm25", "dense", "rrf"}
    assert all(row["complete_evidence_set"] and not row["missing_evidence"] for row in rows)
    assert all(all(hit["rank"] > 0 and isinstance(hit["score"], float) for hit in row["hit_evidence"])
               for row in rows)


def test_frozen_query_set_hash_and_decomposition_trigger():
    assert evaluate.FROZEN_SHA256 == "003e7b11fc8ce3309cc12df140ce408b8f3f42ba58d52a4e093d0832c70a6269"
    from papertrail.qa import _requires_decomposition
    assert _requires_decomposition(evaluate.CASES[2]["query"])


def test_fixture_runner_has_no_network_capability():
    tree = ast.parse((ROOT / "scripts/evaluate_pt2_synthetic.py").read_text(encoding="utf-8"))
    forbidden = {"requests", "httpx", "urllib", "socket", "aiohttp", "websocket"}
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection(forbidden)
