"""Build and evaluate a frozen synthetic evidence retrieval set offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.audit import _hash
from papertrail.retrieval import build_vector_index, retrieve
from papertrail.s1_index import index_selection

FIXTURE_VERSION = "pt2-synthetic-evidence-v1"
CASES = [
    {"id": "SYN-01", "query": "Which method uses amber calibration?", "gold": ["amber calibration protocol"]},
    {"id": "SYN-02", "query": "What result reports cobalt retention?", "gold": ["cobalt retention was 73 percent"]},
    {"id": "SYN-03", "query": "Compare amber calibration and cobalt retention", "gold": ["amber calibration protocol", "cobalt retention was 73 percent"]},
]
FROZEN_SHA256 = hashlib.sha256(json.dumps(CASES, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()
PAGES = [
    ("Synthetic Retrieval Alpha", "Methods", "The amber calibration protocol uses three reference samples before each run."),
    ("Synthetic Retrieval Beta", "Results", "Cobalt retention was 73 percent after the controlled wash cycle."),
    ("Synthetic Retrieval Noise", "Background", "The control panel uses routine weekly inspection and a neutral storage rack."),
]


def build_fixture(directory: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=True)
    docs = directory / "docs"
    docs.mkdir(exist_ok=True)
    selections = []
    hashes = {}
    for index, (title, heading, body) in enumerate(PAGES):
        path = docs / f"synthetic-{index}.pdf"
        document = fitz.open()
        page = document.new_page()
        page.insert_text((40, 50), title, fontsize=16)
        page.insert_text((40, 90), heading, fontsize=13)
        page.insert_text((40, 130), body, fontsize=11)
        document.set_metadata({"title": title})
        document.save(path)
        document.close()
        digest = _hash(path)
        hashes[path.name] = digest
        selections.append({"root_id": "synthetic", "file_name": path.name, "sha256": digest,
                           "kind": "pdf", "source_type": "original_pdf"})
    source_config = directory / "synthetic-sources.yaml"
    source_config.write_text("roots:\n  - id: synthetic\n    path: " + str(docs).replace("\\", "/") + "\n    kinds: [pdf]\n", encoding="utf-8")
    selection_file = directory / "synthetic-selection.jsonl"
    selection_file.write_text("".join(json.dumps(row) + "\n" for row in selections), encoding="utf-8")
    return docs, source_config, selection_file, hashes


def _evidence_key(row: dict) -> str:
    folded = " ".join(row.get("text", "").casefold().split())
    return next((quote for quote in (casefold for casefold in ("amber calibration protocol", "cobalt retention was 73 percent")) if quote in folded), "")


def run(directory: Path, output: Path) -> dict:
    os.environ["HF_HUB_OFFLINE"] = "1"
    _, sources, selection, pdf_hashes = build_fixture(directory)
    db = directory / "synthetic.sqlite3"
    index = index_selection(db, sources, selection)
    vector_artifact = directory / "synthetic-vectors.joblib"
    build_vector_index(db, vector_artifact)
    methods = {"bm25": "bm25", "dense": "vector", "rrf": "hybrid"}
    records = []
    for case in CASES:
        for label, mode in methods.items():
            hits = retrieve(db, case["query"], 20, "original_pdf", mode, vector_artifact)
            found = []
            for rank, hit in enumerate(hits, 1):
                value = _evidence_key(hit)
                if value and value not in [item["evidence"] for item in found]:
                    # BLAS may vary in the last few float32 bits across identical SVD builds.
                    # Keep the report stable while retaining useful score precision.
                    found.append({"evidence": value, "rank": rank, "score": round(float(hit.get("rank_score", 0.0)), 4)})
            found_quotes = [item["evidence"] for item in found]
            missing = [quote for quote in case["gold"] if quote not in found_quotes]
            records.append({"case_id": case["id"], "method": label, "query_sha256": hashlib.sha256(case["query"].encode()).hexdigest(),
                           "gold_evidence": case["gold"], "hit_evidence": found, "missing_evidence": missing,
                           "complete_evidence_set": not missing,
                           "failure_attribution": [] if not missing else ["target evidence absent from returned top-20 chunks"],
                           "returned_chunk_count": len(hits)})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    return {"fixture_version": FIXTURE_VERSION, "frozen_set_sha256": FROZEN_SHA256,
            "index": index, "pdf_sha256": pdf_hashes,
            "results": records, "report_sha256": _hash(output)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.fixture_dir, args.output)
    print(json.dumps({"fixture_version": result["fixture_version"], "cases": len(CASES),
                      "method_runs": len(result["results"]), "report_sha256": result["report_sha256"]}))


if __name__ == "__main__":
    main()
