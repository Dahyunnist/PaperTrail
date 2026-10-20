"""Build the frozen, synthetic-only P12 PaperTrail retrieval benchmark."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

from papertrail.gold import load_gold, verify_quotes
from papertrail.s1_index import index_selection

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "evals" / "p12-synthetic"
GOLD_PATH = ROOT / "evals" / "p12-synthetic-gold.jsonl"
MANIFEST_PATH = ROOT / "evals" / "p12-synthetic-manifest.json"
LOCAL_DIR = ROOT / ".local" / "p12-synthetic"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    pdfs = sorted(FIXTURE_DIR.glob("*.pdf"))
    if len(pdfs) != 2 or not GOLD_PATH.is_file():
        raise SystemExit("P12 requires both committed synthetic PDFs and the frozen gold set")

    source_root = LOCAL_DIR / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    selections = []
    document_hashes = {}
    for source in pdfs:
        destination = source_root / source.name
        shutil.copyfile(source, destination)
        digest = sha256(source)
        document_hashes[source.name] = digest
        selections.append({"root_id": "fixture", "file_name": source.name,
                           "relative_path": source.name, "sha256": digest,
                           "kind": "pdf", "source_type": "original_pdf"})

    sources_path = LOCAL_DIR / "sources.yaml"
    sources_path.write_text(yaml.safe_dump({"roots": [{
        "id": "fixture", "path": str(source_root), "kinds": ["pdf"]
    }]}, allow_unicode=True), encoding="utf-8")
    selection_path = LOCAL_DIR / "selection.jsonl"
    selection_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                                  for row in selections), encoding="utf-8")
    database = LOCAL_DIR / "papertrail.sqlite3"
    for path in (database, database.with_name(database.name + "-wal"),
                 database.with_name(database.name + "-shm")):
        path.unlink(missing_ok=True)
    indexed = index_selection(database, sources_path, selection_path)

    items = load_gold(GOLD_PATH, minimum_questions=6)
    verified = verify_quotes(items, sources_path)
    manifest = {
        "benchmark": "PaperTrail P12 synthetic RAG holdout",
        "data_policy": "synthetic fixtures only; no local thesis material",
        "question_count": len(items),
        "answerable_count": sum(not item["abstain"] for item in items),
        "unanswerable_count": sum(item["abstain"] for item in items),
        "documents": document_hashes,
        "gold_sha256": sha256(GOLD_PATH),
        "verified_evidence_quotes": verified,
        "indexed_chunks": indexed["chunks"],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print(f"questions={len(items)} evidence_quotes_verified={verified} "
          f"documents={len(document_hashes)} chunks={indexed['chunks']}")


if __name__ == "__main__":
    main()
