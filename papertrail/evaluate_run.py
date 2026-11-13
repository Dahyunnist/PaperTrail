"""Run a manifest-bound deterministic retrieval evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evaluate import compare_modes
from .gold import load_gold

RUN_FIELDS = ("schema_version", "project", "git_sha", "dataset_id", "dataset_sha256", "split",
              "model_id", "prompt_sha", "tool_schema_sha", "runtime_digest", "max_steps",
              "max_tokens", "scorer_sha", "gold_source", "cost_usd_estimate", "run_id",
              "trace_id", "started_at", "ended_at", "status", "source_type",
              "source_manifest_sha256", "gold_sha256", "retrieval_modes", "k",
              "question_count", "report_fingerprint")
SENSITIVE_FIELD = re.compile(r"(api.?key|secret|password|token|private.?key|chain.?of.?thought|raw.?prompt)", re.I)


def build_run_manifest(*, git_sha: str, dataset_id: str, dataset_sha256: str, split: str,
                       scorer_sha: str, gold_source: str, started_at: str, ended_at: str,
                       run_id: str, trace_id: str, max_steps: int = 1,
                       status: str = "completed") -> dict[str, Any]:
    return {"schema_version": 1, "project": "papertrail", "git_sha": git_sha,
            "dataset_id": dataset_id, "dataset_sha256": dataset_sha256, "split": split,
            "model_id": "none", "prompt_sha": None, "tool_schema_sha": None,
            "runtime_digest": None, "max_steps": max_steps, "max_tokens": None,
            "scorer_sha": scorer_sha, "gold_source": gold_source,
            "cost_usd_estimate": 0, "run_id": run_id, "trace_id": trace_id,
            "started_at": started_at, "ended_at": ended_at, "status": status}


def validate_run_manifest(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("run manifest must be an object")
    if set(RUN_FIELDS) - value.keys():
        raise ValueError("run manifest fields missing")
    if (not isinstance(value["schema_version"], int) or isinstance(value["schema_version"], bool)
            or value["schema_version"] != 1 or value["project"] != "papertrail"):
        raise ValueError("run manifest identity invalid")
    if any(key != "max_tokens" and SENSITIVE_FIELD.search(str(key)) for key in value):
        raise ValueError("run manifest contains a sensitive field")
    for key in ("git_sha",):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{40}", value[key], re.I):
            raise ValueError(f"run manifest {key} invalid")
    for key in ("dataset_sha256", "scorer_sha", "source_manifest_sha256", "gold_sha256",
                "report_fingerprint"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key], re.I):
            raise ValueError(f"run manifest {key} invalid")
    if value["model_id"] != "none" or any(value[k] is not None for k in
            ("prompt_sha", "tool_schema_sha", "runtime_digest", "max_tokens")):
        raise ValueError("run manifest violates no-model boundary")
    if (not isinstance(value["max_steps"], int) or isinstance(value["max_steps"], bool)
            or value["max_steps"] < 1):
        raise ValueError("run manifest max_steps invalid")
    if (not isinstance(value["cost_usd_estimate"], (int, float))
            or isinstance(value["cost_usd_estimate"], bool)
            or value["cost_usd_estimate"] != 0 or value["status"] != "completed"):
        raise ValueError("run manifest cost or status invalid")
    if not isinstance(value["gold_source"], str) or not value["gold_source"].strip():
        raise ValueError("run manifest gold_source must identify the actual source")
    if any(not isinstance(value[k], str) or not value[k] for k in
           ("dataset_id", "split", "gold_source", "run_id", "trace_id", "started_at", "ended_at",
            "source_type")):
        raise ValueError("run manifest metadata invalid")
    if (not isinstance(value["retrieval_modes"], list) or not value["retrieval_modes"]
            or any(not isinstance(mode, str) or not mode for mode in value["retrieval_modes"])):
        raise ValueError("run manifest retrieval_modes invalid")
    if not isinstance(value["k"], int) or isinstance(value["k"], bool) or value["k"] < 1:
        raise ValueError("run manifest k invalid")
    if (not isinstance(value["question_count"], int) or isinstance(value["question_count"], bool)
            or value["question_count"] < 1):
        raise ValueError("run manifest question_count invalid")
    try:
        started = datetime.fromisoformat(value["started_at"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(value["ended_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("run manifest timestamps must be ISO-8601") from exc
    if started.tzinfo is None or ended.tzinfo is None or ended < started:
        raise ValueError("run manifest timestamp range invalid")


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
    source_type = next((manifest.get(key) for key in ("source_type", "data_policy", "dataset_role")
                        if isinstance(manifest.get(key), str) and manifest[key].strip()), None)
    if source_type is None:
        raise ValueError("source manifest must declare source_type, data_policy, or dataset_role")
    dataset_id = manifest.get("dataset_id", manifest.get("group_id", manifest.get("benchmark")))
    split = manifest.get("split", manifest.get("dataset_role"))
    gold_source = manifest.get("gold_source")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("source manifest must declare dataset_id, group_id, or benchmark")
    if not isinstance(split, str) or not split.strip():
        raise ValueError("source manifest must declare split or dataset_role")
    if not isinstance(gold_source, str) or not gold_source.strip():
        raise ValueError("source manifest must declare gold_source")
    declared_gold = manifest.get("gold_file")
    if declared_gold is not None:
        declared_path = Path(declared_gold)
        candidates = [declared_path, source_manifest.parent / declared_path]
        if not any(candidate.resolve() == gold_path.resolve() for candidate in candidates):
            raise ValueError("gold path does not match source manifest gold_file")
    expected_gold_hash = manifest.get("gold_sha256")
    actual_gold_hash = sha256(gold_path)
    if (not isinstance(expected_gold_hash, str) or len(expected_gold_hash) != 64
            or expected_gold_hash != actual_gold_hash):
        raise ValueError("gold SHA-256 does not match source manifest")
    expected_count = manifest.get("question_count")
    items = load_gold(gold_path, minimum_questions=minimum_questions)
    if expected_count is not None and (
            not isinstance(expected_count, int) or isinstance(expected_count, bool)
            or expected_count != len(items)):
        raise ValueError("manifest question_count does not match validated gold")
    if not modes or k < 1:
        raise ValueError("at least one retrieval mode and k >= 1 are required")

    started_at = datetime.now(timezone.utc).isoformat()
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
            "source_type": source_type,
            "question_count": len(items),
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
            "unanswerable_questions": len(items) - raw["answerable_questions"],
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
    ended_at = datetime.now(timezone.utc).isoformat()
    report["dataset"]["dataset_id"] = dataset_id
    report["run_manifest"] = build_run_manifest(
        git_sha=report["provenance"]["git_sha"], dataset_id=report["dataset"]["dataset_id"],
        dataset_sha256=hashlib.sha256(json.dumps({
            "source_manifest_sha256": sha256(source_manifest), "gold_sha256": actual_gold_hash,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        split=split,
        scorer_sha=sha256(Path(__file__)), gold_source=gold_source,
        started_at=started_at, ended_at=ended_at,
        run_id=hashlib.sha256((report["provenance"]["git_sha"] + actual_gold_hash + started_at).encode()).hexdigest()[:32],
        trace_id=hashlib.sha256((actual_gold_hash + started_at).encode()).hexdigest()[:32],
        max_steps=1)
    report["run_manifest"].update({"source_type": source_type,
        "source_manifest_sha256": report["provenance"]["source_manifest_sha256"],
        "gold_sha256": actual_gold_hash, "retrieval_modes": list(modes), "k": k,
        "question_count": len(items), "report_fingerprint": "0" * 64})
    validate_run_manifest(report["run_manifest"])
    fingerprint_body = json.dumps(report, ensure_ascii=False, sort_keys=True).encode()
    report["run_manifest"]["report_fingerprint"] = hashlib.sha256(fingerprint_body).hexdigest()
    validate_run_manifest(report["run_manifest"])
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
