"""Validate PT-1 v2 human gold, then convert it to the runtime gold schema."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from papertrail.gold import load_gold, verify_quotes
from validate_pt1_gold_jsonl import DEFAULT_MANIFEST, validate


def convert(v2_path: Path, gold_output: Path, sources_output: Path,
            manifest_path: Path = DEFAULT_MANIFEST, min_questions: int = 40,
            min_papers: int = 30) -> tuple[int, int]:
    if v2_path.resolve() in {gold_output.resolve(), sources_output.resolve()}:
        raise ValueError("input v2 JSONL cannot be used as an output path")
    if gold_output.resolve() == sources_output.resolve():
        raise ValueError("gold output and sources output must be different files")

    problems = validate(v2_path, manifest_path, min_questions=min_questions, min_papers=min_papers)
    if problems:
        raise ValueError("PT1 v2 validation failed:\n" + "\n".join(problems))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_map = {entry["doi"]: entry for entry in manifest["sources"]}
    rows = [json.loads(line) for line in v2_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    runtime_rows: list[dict[str, Any]] = []
    runtime_roots: dict[str, dict[str, str]] = {}
    for row in rows:
        evidence = []
        for doi in row["paper_ids"]:
            source = source_map[doi]
            pdf_path = (ROOT / source["local_pdf"]).resolve()
            root_id = "pt1-" + hashlib.sha256(doi.encode("utf-8")).hexdigest()[:12]
            runtime_roots[root_id] = {"id": root_id, "path": str(pdf_path.parent)}
        for citation in row["evidence"]:
            source = source_map[citation["doi"]]
            pdf_path = (ROOT / source["local_pdf"]).resolve()
            root_id = "pt1-" + hashlib.sha256(citation["doi"].encode("utf-8")).hexdigest()[:12]
            evidence.append({
                "root_id": root_id,
                "file_name": pdf_path.name,
                "sha256": citation["pdf_sha256"],
                "pdf_page": citation["pdf_page"],
                "quote": citation["quote"],
                "relation": citation["relation"],
            })
        runtime_rows.append({
            "id": row["id"],
            "question_type": row["question_type"],
            "question": row["question"],
            "expected_answer": row["expected_answer"],
            "abstain": row["answerability"] == "unanswerable",
            "evidence": evidence,
            # Retain PT1 review provenance; runtime consumers may ignore these fields.
            "paper_ids": row["paper_ids"],
            "split": row["split"],
            "minimumCompleteEvidenceSet": row["minimumCompleteEvidenceSet"],
            "annotation_status": row["annotation_status"],
            "annotator": row["annotator"],
            "reviewer": row["reviewer"],
        })

    sources_config = {"roots": list(runtime_roots.values())}
    gold_output.parent.mkdir(parents=True, exist_ok=True)
    sources_output.parent.mkdir(parents=True, exist_ok=True)
    gold_temp = gold_output.with_name(gold_output.name + ".partial")
    sources_temp = sources_output.with_name(sources_output.name + ".partial")
    try:
        gold_temp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in runtime_rows), encoding="utf-8")
        # JSON is valid YAML and avoids an extra serialization format dependency.
        sources_temp.write_text(json.dumps(sources_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        loaded = load_gold(gold_temp, minimum_questions=min_questions)
        verified_quotes = verify_quotes(loaded, sources_temp)
        if verified_quotes != sum(len(row["evidence"]) for row in runtime_rows):
            raise ValueError("runtime quote verification count mismatch")
        gold_temp.replace(gold_output)
        sources_temp.replace(sources_output)
    finally:
        gold_temp.unlink(missing_ok=True)
        sources_temp.unlink(missing_ok=True)
    return len(runtime_rows), verified_quotes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v2_jsonl", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-gold", type=Path, required=True)
    parser.add_argument("--output-sources", type=Path, required=True)
    parser.add_argument("--min-questions", type=int, default=40)
    parser.add_argument("--min-papers", type=int, default=30)
    args = parser.parse_args()
    count, quote_count = convert(
        args.v2_jsonl, args.output_gold, args.output_sources, args.manifest,
        args.min_questions, args.min_papers,
    )
    print(f"Imported {count} human-verified questions; verified {quote_count} source quotes.")


if __name__ == "__main__":
    main()
