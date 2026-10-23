"""Evaluate frozen PT1 gold on local indexes without sending corpus data to a service."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.gold import _normalize_excerpt, load_gold, verify_quotes
from papertrail.retrieval import build_vector_index, retrieve


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _metrics(items: list[dict], ranked: dict[str, list[dict]], k: int) -> dict:
    recalls = []
    reciprocal_ranks = []
    candidate_precisions = []
    complete_pages = 0
    complete_evidence = 0
    per_question = {}
    for item in items:
        rows = ranked[item["id"]]
        pages = []
        for row in rows:
            key = (row["sha256"], row["pdf_page"])
            if key not in pages:
                pages.append(key)
        gold_pages = {(pointer["sha256"], pointer["pdf_page"]) for pointer in item["evidence"]}
        found_pages = gold_pages.intersection(pages)
        recalls.append(len(found_pages) / len(gold_pages) if gold_pages else 1.0)
        complete_pages += int(found_pages == gold_pages)
        candidate_precisions.append(len(found_pages) / len(pages) if pages else 0.0)
        rank = next((index for index, page in enumerate(pages, 1) if page in gold_pages), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
        quote_hits = [any(
            row["sha256"] == pointer["sha256"] and row["pdf_page"] == pointer["pdf_page"]
            and _normalize_excerpt(pointer["quote"]) in _normalize_excerpt(row["text"])
            for row in rows
        ) for pointer in item["evidence"]]
        complete_evidence += int(all(quote_hits))
        per_question[item["id"]] = {
            "first_gold_page_rank": rank,
            "gold_pages_found": len(found_pages),
            "gold_pages_total": len(gold_pages),
            "evidence_items_found": sum(quote_hits),
            "evidence_items_total": len(quote_hits),
        }
    return {
        "gold_page_recall": round(statistics.mean(recalls), 4),
        "mrr": round(statistics.mean(reciprocal_ranks), 4),
        "complete_gold_page_questions": complete_pages,
        "candidate_page_precision": round(statistics.mean(candidate_precisions), 4),
        "complete_evidence_questions": complete_evidence,
        "per_question": per_question,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=ROOT / ".local/pt1-real-dev-gold.jsonl")
    parser.add_argument("--manifest", type=Path, default=ROOT / ".local/pt1-real-dev-manifest.json")
    parser.add_argument("--sources", type=Path, default=ROOT / "configs/sources.example.yaml")
    parser.add_argument("--database", type=Path, default=ROOT / ".local/papertrail-expanded-s1.sqlite3")
    parser.add_argument("--artifact", type=Path, default=ROOT / ".local/pt1-expanded-vectors.joblib")
    parser.add_argument("--out", type=Path, default=ROOT / ".local/pt2-real-retrieval.json")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    gold_digest = _sha256(args.gold)
    if gold_digest != manifest["gold_sha256"]:
        raise SystemExit("PT1 黄金集哈希与冻结清单不匹配")
    items = load_gold(args.gold, minimum_questions=1)
    verified = verify_quotes(items, args.sources)
    if not args.artifact.exists():
        build_vector_index(args.database, args.artifact)

    report = {
        "dataset_id": manifest["dataset_id"],
        "gold_sha256": gold_digest,
        "question_count": len(items),
        "verified_evidence_quotes": verified,
        "privacy": "local_only_no_model_api",
        "modes": {},
    }
    for mode in ("bm25", "vector", "hybrid"):
        mode_result = {}
        for k in (5, 10):
            ranked = {}
            latencies = []
            for item in items:
                started = time.perf_counter()
                ranked[item["id"]] = retrieve(args.database, item["question"], k,
                                               source_type="original_pdf", mode=mode,
                                               artifact=args.artifact)
                latencies.append((time.perf_counter() - started) * 1000)
            metrics = _metrics(items, ranked, k)
            metrics["latency_ms_mean"] = round(statistics.mean(latencies), 2)
            metrics["latency_ms_median"] = round(statistics.median(latencies), 2)
            mode_result[str(k)] = metrics
        report["modes"][mode] = mode_result
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "questions": len(items),
                      "modes": list(report["modes"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
