from __future__ import annotations

import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

from papertrail.evaluate_run import build_run_manifest
from scripts.evaluate_pt17_retrieval_comparison import (
    MODES,
    KS,
    _assert_tracked_worktree_clean,
    build_comparison_report,
)


class PT17RetrievalComparisonTests(unittest.TestCase):
    def setUp(self):
        self.hashes = {
            "git_sha": "a" * 40,
            "source_manifest_sha256": "b" * 64,
            "gold_sha256": "c" * 64,
            "runner_sha256": "d" * 64,
        }
        self.evaluations = []
        for k in KS:
            manifest = build_run_manifest(
                git_sha=self.hashes["git_sha"], dataset_id="pt17-public-heldout-20261023",
                dataset_sha256="e" * 64, split="final_paper_disjoint_holdout",
                scorer_sha="f" * 64, gold_source="fixture-test",
                started_at="2026-11-13T00:00:00+00:00",
                ended_at="2026-11-13T00:00:01+00:00", run_id=f"run-{k}", trace_id=f"trace-{k}")
            manifest.update({
                "source_type": "final_paper_disjoint_holdout",
                "source_manifest_sha256": self.hashes["source_manifest_sha256"],
                "gold_sha256": self.hashes["gold_sha256"],
                "retrieval_modes": list(MODES), "k": k, "question_count": 5,
                "report_fingerprint": "0" * 64,
            })
            self.evaluations.append({
                "run_manifest": manifest,
                "evaluation": {"k": k, "modes": {mode: {"page_recall_at_k": 0.5} for mode in MODES}},
            })

    def test_builds_six_run_non_generation_report_with_provenance(self):
        report = build_comparison_report(
            evaluations=self.evaluations, **self.hashes, created_at_utc="2026-11-13T00:00:00+00:00")
        self.assertEqual(len(report["evaluations"]), 2)
        self.assertFalse(report["generation"])
        self.assertEqual(report["provenance"]["gold_sha256"], "c" * 64)
        self.assertEqual(report["provenance"]["source_manifest_sha256"], "b" * 64)
        self.assertEqual(report["evaluations"][0]["run_manifest"]["k"], 5)

    def test_rejects_missing_gold_hash(self):
        with self.assertRaisesRegex(ValueError, "gold_sha256"):
            build_comparison_report(
                evaluations=self.evaluations, **{**self.hashes, "gold_sha256": ""},
                created_at_utc="2026-11-13T00:00:00+00:00")

    def test_refuses_to_run_with_tracked_changes(self):
        result = CompletedProcess(args=[], returncode=0, stdout=" M scripts/evaluator.py\n", stderr="")
        with patch("scripts.evaluate_pt17_retrieval_comparison.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "commit tracked code changes"):
                _assert_tracked_worktree_clean()

    def test_rejects_incomplete_k_or_mode_runs(self):
        with self.assertRaisesRegex(ValueError, "one manifest-bound evaluation per k"):
            build_comparison_report(
                evaluations=self.evaluations[:1], **self.hashes,
                created_at_utc="2026-11-13T00:00:00+00:00")
        invalid = [{"run_manifest": row["run_manifest"], "evaluation": dict(row["evaluation"])}
                   for row in self.evaluations]
        invalid[0]["evaluation"]["modes"].pop("hybrid")
        with self.assertRaisesRegex(ValueError, "BM25/vector/hybrid"):
            build_comparison_report(
                evaluations=invalid, **self.hashes,
                created_at_utc="2026-11-13T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
