"""Validate human-reviewed PT-1 JSONL annotations against the frozen PDF manifest."""
from __future__ import annotations

import hashlib
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSONL = ROOT / "evals/pt1-candidate-gold-20261111.jsonl"
DEFAULT_MANIFEST = ROOT / "evals/pt1-candidate-manifest-20261111.json"
RELATIONS = {"supports", "contradicts", "context"}
TYPES = {"fact_location", "method_comparison", "cross_paper", "multi_hop", "conflict", "unanswerable"}


def normalize_question(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def validate(path: Path = DEFAULT_JSONL, manifest_path: Path = DEFAULT_MANIFEST,
             min_questions: int = 40, min_papers: int = 30) -> list[str]:
    issues: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {item["doi"]: item for item in manifest["sources"]}
    documents: dict[str, pymupdf.Document] = {}
    hashes: dict[str, str] = {}
    ids: set[str] = set()
    questions: set[str] = set()
    paper_ids: set[str] = set()

    def source_document(doi: str, line_no: int) -> pymupdf.Document | None:
        if doi not in sources:
            issues.append(f"line {line_no}: unknown DOI")
            return None
        if doi not in documents:
            source = sources[doi]
            pdf_path = (ROOT / source["local_pdf"]).resolve()
            if ROOT.resolve() not in pdf_path.parents:
                issues.append(f"line {line_no}: PDF path escapes repository")
                return None
            try:
                data = pdf_path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if digest != source["pdf_sha256"]:
                    issues.append(f"line {line_no}: manifest PDF hash mismatch")
                    return None
                hashes[doi] = digest
                documents[doi] = pymupdf.open(pdf_path)
            except (OSError, RuntimeError) as exc:
                issues.append(f"line {line_no}: cannot read manifest PDF ({type(exc).__name__})")
                return None
        return documents[doi]

    try:
        for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                issues.append(f"line {line_no}: invalid JSON")
                continue
            if not isinstance(row, dict):
                issues.append(f"line {line_no}: record must be an object")
                continue
            required = {"id", "paper_ids", "split", "question_type", "question", "expected_answer",
                        "answerability", "evidence", "minimumCompleteEvidenceSet", "annotation_status",
                        "annotator", "reviewer"}
            missing = required - row.keys()
            if missing:
                issues.append(f"line {line_no}: missing required fields")
                continue
            record_id = row["id"]
            if not isinstance(record_id, str) or not record_id.strip() or record_id in ids:
                issues.append(f"line {line_no}: id must be nonempty and unique")
            ids.add(record_id if isinstance(record_id, str) else "")
            question = row["question"]
            if not isinstance(question, str) or not question.strip():
                issues.append(f"line {line_no}: question must be nonempty")
            else:
                normalized = normalize_question(question)
                if normalized in questions:
                    issues.append(f"line {line_no}: duplicate normalized question")
                questions.add(normalized)
            if row["split"] != "development" or not isinstance(row["question_type"], str) or row["question_type"] not in TYPES:
                issues.append(f"line {line_no}: invalid split or question_type")
            if row["annotation_status"] != "human_verified" or not row["annotator"] or not row["reviewer"] or row["annotator"] == row["reviewer"]:
                issues.append(f"line {line_no}: human review incomplete or reviewer matches annotator")
            if row["minimumCompleteEvidenceSet"] is not True:
                issues.append(f"line {line_no}: minimumCompleteEvidenceSet must be true")
            paper_list = row["paper_ids"]
            if (not isinstance(paper_list, list) or not paper_list
                    or any(not isinstance(item, str) for item in paper_list)
                    or len(set(item for item in paper_list if isinstance(item, str))) != len(paper_list)):
                issues.append(f"line {line_no}: paper_ids must be a nonempty unique list")
                paper_list = []
            paper_ids.update(item for item in paper_list if isinstance(item, str))
            evidence = row["evidence"]
            if not isinstance(evidence, list):
                issues.append(f"line {line_no}: evidence must be a list")
                evidence = []
            answerability = row["answerability"]
            if not isinstance(answerability, str) or answerability not in {"answerable", "unanswerable"}:
                issues.append(f"line {line_no}: invalid answerability")
            if answerability == "answerable" and (not isinstance(row["expected_answer"], str) or not row["expected_answer"].strip() or not evidence):
                issues.append(f"line {line_no}: answerable record needs answer and evidence")
            if answerability == "unanswerable" and (not isinstance(row["expected_answer"], str) or not row["expected_answer"].strip() or evidence):
                issues.append(f"line {line_no}: unanswerable record needs refusal rationale and empty evidence")
            evidence_dois: set[str] = set()
            relations: set[str] = set()
            for entry in evidence:
                if not isinstance(entry, dict):
                    issues.append(f"line {line_no}: evidence entry must be an object")
                    continue
                required_evidence = {"doi", "pdf_sha256", "pdf_page", "start_char", "end_char", "quote", "relation"}
                if required_evidence - entry.keys():
                    issues.append(f"line {line_no}: evidence reference missing fields")
                    continue
                doi, rel = entry["doi"], entry["relation"]
                if doi not in paper_list:
                    issues.append(f"line {line_no}: evidence DOI absent from paper_ids")
                evidence_dois.add(doi)
                if not isinstance(rel, str) or rel not in RELATIONS:
                    issues.append(f"line {line_no}: invalid evidence relation")
                else:
                    relations.add(rel)
                doc = source_document(doi, line_no) if isinstance(doi, str) else None
                if doc is None:
                    continue
                if entry["pdf_sha256"] != hashes.get(doi):
                    issues.append(f"line {line_no}: evidence PDF hash mismatch")
                page_no = entry["pdf_page"]
                start, end, quote = entry["start_char"], entry["end_char"], entry["quote"]
                if not isinstance(page_no, int) or not 1 <= page_no <= doc.page_count:
                    issues.append(f"line {line_no}: evidence PDF page out of range")
                    continue
                page_text = doc[page_no - 1].get_text("text")
                if not isinstance(start, int) or not isinstance(end, int) or not isinstance(quote, str) or start < 0 or end <= start or end > len(page_text) or page_text[start:end] != quote:
                    issues.append(f"line {line_no}: quote/span does not match PDF page text")
            qtype = row["question_type"]
            if qtype in {"cross_paper", "method_comparison", "multi_hop"} and len(evidence_dois) < 2:
                issues.append(f"line {line_no}: cross-paper question needs evidence from two papers")
            if qtype == "conflict" and (len(evidence_dois) < 2 or not {"supports", "contradicts"} <= relations):
                issues.append(f"line {line_no}: conflict needs supporting and contradicting evidence from two papers")
    finally:
        for document in documents.values():
            document.close()
    if len(ids) < min_questions:
        issues.append(f"expected at least {min_questions} questions, got {len(ids)}")
    if len(paper_ids) < min_papers:
        issues.append(f"expected at least {min_papers} papers, got {len(paper_ids)}")
    return issues


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", nargs="?", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--min-questions", type=int, default=40)
    parser.add_argument("--min-papers", type=int, default=30)
    args = parser.parse_args()
    found = validate(args.jsonl, min_questions=args.min_questions, min_papers=args.min_papers)
    if found:
        print("\n".join(found))
        raise SystemExit(1)
    print("PT1 JSONL valid: human-reviewed answers, paper/page/quote references match PDFs.")
