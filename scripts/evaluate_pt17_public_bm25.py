"""Rebuild the registered public PT17 fixture index and run deterministic BM25."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.evaluate_run import run_evaluation
from papertrail.s1_index import index_selection

MANIFEST = ROOT / "evals/pt17-heldout-source-manifest-20261023.json"
EXPECTED_FIXTURE_DIR = (ROOT / "evals/fixtures/pt17-heldout").resolve()


def _prepare(work_dir: Path) -> tuple[Path, Path, Path]:
    manifest: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    work_dir.mkdir(parents=True, exist_ok=True)
    database = work_dir / "index.sqlite3"
    if database.exists():
        raise ValueError("work directory already contains an index; choose a fresh directory")

    root_id = "pt17-public-heldout"
    selection_rows = []
    for paper in manifest.get("sources", []):
        if paper.get("license", manifest.get("license")) != "CC BY 4.0":
            raise ValueError("PT17 fixture must have registered CC BY 4.0 license")
        source = (ROOT / paper["local_pdf"]).resolve()
        if EXPECTED_FIXTURE_DIR not in source.parents or not source.is_file():
            raise ValueError("PT17 source is missing or outside the registered public fixture directory")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        expected = paper.get("local_pdf_sha256", paper.get("sha256"))
        if digest != expected:
            raise ValueError(f"PT17 source hash mismatch: {source.name}")
        selection_rows.append({
            "root_id": root_id,
            "file_name": source.name,
            "relative_path": source.name,
            "sha256": digest,
            "kind": "pdf",
            "source_type": "original_pdf",
        })
    if not selection_rows:
        raise ValueError("PT17 source manifest has no registered sources")

    sources = work_dir / "sources.yaml"
    sources.write_text(json.dumps({"roots": [{"id": root_id, "path": str(EXPECTED_FIXTURE_DIR)}]},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    selection = work_dir / "selection.jsonl"
    selection.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                         for row in selection_rows), encoding="utf-8")
    indexed = index_selection(database, sources, selection)
    if indexed.get("selected") != len(selection_rows) or indexed.get("issues"):
        raise RuntimeError(f"PT17 fixture indexing failed: {indexed}")
    return database, sources, selection


def run(work_dir: Path, report_path: Path) -> dict[str, Any]:
    database, _sources, _selection = _prepare(work_dir)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    gold_path = ROOT / manifest["gold_file"]
    return run_evaluation(database, gold_path, MANIFEST, report_path,
                          k=5, modes=("bm25",), minimum_questions=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".tmp/pt17-public-bm25")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "reports/pt17-public-bm25-20261113.json")
    args = parser.parse_args()
    report = run(args.work_dir, args.report)
    metrics = report["evaluation"]["modes"]["bm25"]
    print(json.dumps({
        "report": str(args.report),
        "dataset_id": report["run_manifest"]["dataset_id"],
        "question_count": report["run_manifest"]["question_count"],
        "gold_source": report["run_manifest"]["gold_source"],
        "answerable_questions": report["evaluation"]["answerable_questions"],
        "unanswerable_questions": report["evaluation"]["unanswerable_questions"],
        "page_recall_at_5": metrics["page_recall_at_k"],
        "gold_page_recall_at_5": metrics["gold_page_recall_at_k"],
        "document_recall_at_5": metrics["document_recall_at_k"],
        "complete_evidence_at_5": metrics["complete_evidence_at_k"],
        "ndcg_at_5": metrics["ndcg_at_k"],
        "unanswerable_retrieval_nonempty": any(
            item["retrieval_nonempty"]
            for item in report["evaluation"]["modes"]["bm25"]["unanswerable_retrieval"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
