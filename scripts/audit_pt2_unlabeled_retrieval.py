"""Rebuild a local BM25 index from explicit inputs and emit a no-gold audit trace."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.retrieval import retrieve
from papertrail.s1_index import index_selection, open_database


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(database: Path, sources: Path, selection: Path, queries_path: Path,
        output: Path, *, limit: int = 10) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    queries = [json.loads(line) for line in queries_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not queries or any(not isinstance(row, dict) or not isinstance(row.get("id"), str)
                          or not isinstance(row.get("query"), str) or not row["query"].strip()
                          for row in queries):
        raise ValueError("queries must be non-empty JSONL rows with id and query")
    if len({row["id"] for row in queries}) != len(queries):
        raise ValueError("query IDs must be unique")
    index_result = index_selection(database, sources, selection, reconcile=True)
    results = []
    for query in queries:
        hits = retrieve(database, query["query"], limit, source_type="original_pdf", mode="bm25")
        results.append({
            "query_id": query["id"],
            "query_sha256": hashlib.sha256(query["query"].encode("utf-8")).hexdigest(),
            "candidate_count": len(hits),
            "hits": [{"rank": rank, "document_sha256": hit["sha256"],
                      "pdf_page": hit["pdf_page"], "chunk_id": hit["chunk_id"],
                      "score": round(float(hit["rank_score"]), 8)}
                     for rank, hit in enumerate(hits, 1)],
        })
    try:
        git_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                 capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        git_sha = "unknown"
    conn = open_database(database, readonly=True)
    try:
        index_revision = int(conn.execute(
            "SELECT value FROM app_metadata WHERE key='index_revision'").fetchone()[0])
    finally:
        conn.close()
    report = {
        "schema_version": 1, "run_type": "unlabeled_retrieval_audit",
        "git_sha": git_sha, "split": "unlabeled_local_audit",
        "runtime": f"CPython {platform.python_version()} / {platform.platform()}",
        "started_at": started_at, "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "gold_source": None, "gold_metrics": None, "model_id": None, "cost_usd": None,
        "input_sha256": {"sources_config": sha256(sources), "selection_manifest": sha256(selection),
                         "queries": sha256(queries_path)},
        "database_index_revision": index_revision,
        "index_counts": {key: index_result[key] for key in ("selected", "added", "duplicates")},
        "query_count": len(results), "limit": limit, "results": results,
        "privacy": "query text, document text, titles, local paths, prompts, and secrets omitted",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    report = run(args.database, args.sources, args.selection, args.queries, args.output, limit=args.limit)
    print(json.dumps({"run_type": report["run_type"], "query_count": report["query_count"],
                      "gold_metrics": None, "model_id": None, "cost_usd": None}))


if __name__ == "__main__":
    main()
