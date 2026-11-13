"""Run deterministic PT17 retrieval comparison on the registered public fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.evaluate_run import (
    run_evaluation,
    sha256 as file_sha256,
    validate_run_manifest,
)
from scripts.evaluate_pt17_public_bm25 import MANIFEST, _prepare

MODES = ("bm25", "vector", "hybrid")
KS = (5, 10)
REPORT_SCHEMA_VERSION = 1


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _assert_tracked_worktree_clean() -> None:
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if changed:
        raise RuntimeError("commit tracked code changes before evaluation so git_sha identifies the runner")


def build_comparison_report(*, evaluations: list[dict[str, Any]], git_sha: str,
                            source_manifest_sha256: str, gold_sha256: str,
                            runner_sha256: str, created_at_utc: str) -> dict[str, Any]:
    if len(git_sha) != 40 or any(c not in "0123456789abcdef" for c in git_sha.lower()):
        raise ValueError("git_sha must be a full hexadecimal commit SHA")
    for name, value in (("source_manifest_sha256", source_manifest_sha256),
                         ("gold_sha256", gold_sha256), ("runner_sha256", runner_sha256)):
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value.lower()):
            raise ValueError(f"{name} must be a full SHA-256")
    if len(evaluations) != len(KS):
        raise ValueError("comparison must contain one manifest-bound evaluation per k")
    by_k = {row.get("evaluation", {}).get("k"): row for row in evaluations}
    if set(by_k) != set(KS):
        raise ValueError("comparison must cover exactly k=5 and k=10")
    for k, item in by_k.items():
        evaluation = item["evaluation"]
        manifest = item.get("run_manifest", {})
        validate_run_manifest(manifest)
        if set(evaluation.get("modes", {})) != set(MODES):
            raise ValueError("each evaluation must compare BM25/vector/hybrid")
        if (manifest.get("k") != k or set(manifest.get("retrieval_modes", [])) != set(MODES)
                or manifest.get("gold_sha256") != gold_sha256
                or manifest.get("source_manifest_sha256") != source_manifest_sha256
                or manifest.get("model_id") != "none"
                or manifest.get("cost_usd_estimate") != 0):
            raise ValueError("nested run manifest does not match the frozen retrieval-only inputs")
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_id": "pt17-public-heldout-20261023",
        "status": "five-question-diagnostic-non-tuning",
        "question_count": 5,
        "generation": False,
        "provenance": {
            "git_sha": git_sha.lower(),
            "source_manifest_sha256": source_manifest_sha256.lower(),
            "gold_sha256": gold_sha256.lower(),
            "runner_sha256": runner_sha256.lower(),
        },
        "created_at_utc": created_at_utc,
        "scope_limit": "仅5道冻结公开题的检索诊断；不得用于调参、泛化或统计显著性结论。",
        # Keep each complete run object so its schema-v1 run manifest and
        # report fingerprint remain attached to the exact evaluated payload.
        "evaluations": [by_k[k] for k in KS],
    }


def run(report_path: Path) -> dict[str, Any]:
    _assert_tracked_worktree_clean()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    gold_path = (ROOT / manifest["gold_file"]).resolve()
    if not gold_path.is_file() or file_sha256(gold_path) != manifest.get("gold_sha256"):
        raise ValueError("registered PT17 gold is missing or its SHA-256 changed")
    manifest_sha = file_sha256(MANIFEST)
    gold_sha = file_sha256(gold_path)
    evaluations: list[dict[str, Any]] = []

    # Keep generated index and intermediate reports in ignored scratch space.
    scratch_root = ROOT / ".tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="pt17-retrieval-comparison-", dir=scratch_root) as temp:
        scratch = Path(temp)
        database, _sources, _selection = _prepare(scratch / "index")
        for k in KS:
            raw_path = scratch / f"k{k}.json"
            result = run_evaluation(database, gold_path, MANIFEST, raw_path,
                                    k=k, modes=MODES, minimum_questions=5)
            if result["provenance"]["gold_sha256"] != gold_sha:
                raise RuntimeError("evaluation runner reported an unexpected gold hash")
            if result["provenance"]["source_manifest_sha256"] != manifest_sha:
                raise RuntimeError("evaluation runner reported an unexpected source manifest hash")
            if result["run_manifest"]["model_id"] != "none" or result["run_manifest"]["cost_usd_estimate"] != 0:
                raise RuntimeError("PT17 retrieval comparison crossed the no-model boundary")
            evaluations.append(result)

    report = build_comparison_report(
        evaluations=evaluations, git_sha=_git_sha(), source_manifest_sha256=manifest_sha,
        gold_sha256=gold_sha, runner_sha256=file_sha256(Path(__file__)),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "reports/pt17-retrieval-comparison-20261113.json")
    args = parser.parse_args()
    report = run(args.report)
    for item in report["evaluations"]:
        evaluation = item["evaluation"]
        for mode, metrics in evaluation["modes"].items():
            mean_ms = item["runtime"]["query_latency_by_mode"][mode]["mean_query_ms"]
            print(f"{mode} k={evaluation['k']}: page_recall={metrics['page_recall_at_k']:.3f} "
                  f"complete_evidence={metrics['complete_evidence_at_k']:.3f} "
                  f"mean_query_ms={mean_ms:.1f}")
    print(f"questions={report['question_count']} gold_sha256={report['provenance']['gold_sha256']} "
          f"report={args.report}")


if __name__ == "__main__":
    main()
