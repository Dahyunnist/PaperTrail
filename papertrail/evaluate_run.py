"""Run a manifest-bound deterministic retrieval evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evaluate import compare_modes
from .gold import load_gold


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def run_evaluation(
    database: Path,
    gold_path: Path,
    source_manifest: Path,
    report_path: Path,
    *,
    k: int = 5,
    modes: tuple[str, ...] = ("bm25", "vector", "hybrid"),
    minimum_questions: int = 1,
) -> dict[str, Any]:
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("source manifest must be a JSON object")
    expected_gold_hash = manifest.get("gold_sha256")
    actual_gold_hash = sha256(gold_path)
    if (not isinstance(expected_gold_hash, str) or len(expected_gold_hash) != 64
            or expected_gold_hash != actual_gold_hash):
        raise ValueError("gold SHA-256 does not match source manifest")
    expected_count = manifest.get("question_count")
    items = load_gold(gold_path, minimum_questions=minimum_questions)
    if isinstance(expected_count, int) and expected_count != len(items):
        raise ValueError("manifest question_count does not match validated gold")
    if not modes or k < 1:
        raise ValueError("at least one retrieval mode and k >= 1 are required")

    started = time.perf_counter()
    raw = compare_modes(database, gold_path, k=k, modes=modes,
                        minimum_questions=minimum_questions)
    elapsed_ms = (time.perf_counter() - started) * 1000

    runtime_by_mode: dict[str, dict[str, float]] = {}
    clean_modes: dict[str, Any] = {}
    for mode, values in raw["modes"].items():
        clean = dict(values)
        runtime_by_mode[mode] = {"mean_query_ms": clean.pop("mean_query_ms")}
        clean_modes[mode] = clean

    report = {
        "schema_version": 1,
        "dataset": {
            "dataset_id": manifest.get("dataset_id", manifest.get("benchmark", "unspecified")),
            "source_type": manifest.get("source_type", manifest.get("data_policy", "unspecified")),
            "question_count": manifest.get("question_count", raw["answerable_questions"]),
        },
        "provenance": {
            "git_sha": _git_sha(),
            "gold_sha256": actual_gold_hash,
            "source_manifest_sha256": sha256(source_manifest),
        },
        "evaluation": {
            "k": k,
            "minimum_questions": minimum_questions,
            "answerable_questions": raw["answerable_questions"],
            "unanswerable_questions": sum(
                1 for row in raw["modes"][modes[0]]["unanswerable_retrieval"]
            ) if modes else 0,
            "modes": clean_modes,
        },
        "runtime": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "elapsed_ms": elapsed_ms,
            "query_latency_by_mode": runtime_by_mode,
        },
        "limits": manifest.get("limits", []),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--minimum-questions", type=int, default=1)
    parser.add_argument("--modes", nargs="+", default=["bm25", "vector", "hybrid"],
                        choices=["bm25", "vector", "hybrid", "bge", "hybrid_bge",
                                 "hybrid_bge_wide", "hybrid_bge_dense_rerank", "hybrid_bge_rerank"])
    args = parser.parse_args()
    report = run_evaluation(args.db, args.gold, args.manifest, args.report,
                            k=args.k, modes=tuple(args.modes),
                            minimum_questions=args.minimum_questions)
    print(f"questions={report['evaluation']['answerable_questions']} "
          f"gold_sha256={report['provenance']['gold_sha256']} report={args.report}")


if __name__ == "__main__":
    main()
