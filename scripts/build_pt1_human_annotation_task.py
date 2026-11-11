"""Build an offline, unannotated 40-question PT-1 human task from PDF headings."""
from __future__ import annotations
import csv
import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals/pt1-candidate-manifest-20261111.json"
OUTPUT = ROOT / "evals/pt1-human-annotation-task-40-20261111.csv"
FIELDS = [
    "task_id", "paper_split", "doi", "title", "pdf_sha256",
    "candidate_type", "candidate_question", "candidate_basis", "candidate_basis_pdf_page",
    "question_type", "answerability", "expected_answer", "minimal_complete_evidence_quote",
    "evidence_pdf_pages", "original_pdf_excerpt", "span_start_char", "span_end_char",
    "annotator", "reviewer", "review_status", "notes",
]
EMPTY_FIELDS = FIELDS[9:]
RULE = re.compile(r"^(?:Rule|Tip)\s*\d+\s*[.:]?\s*(.+)$", re.IGNORECASE)


def headings(source: dict) -> list[tuple[int, str]]:
    document = pymupdf.open(ROOT / source["local_pdf"])
    found: list[tuple[int, str]] = []
    for page_no, page in enumerate(document, start=1):
        for line in page.get_text("text").splitlines():
            clean = " ".join(line.split()).strip()
            match = RULE.match(clean)
            if match:
                title = match.group(1).strip(" .:;-")
                if len(title) >= 5 and (page_no, title) not in found:
                    found.append((page_no, title))
    return found


def build_rows(manifest: dict) -> list[dict[str, str]]:
    sources = sorted(manifest["sources"], key=lambda item: item["doi"])
    rows: list[dict[str, str]] = []
    source_headings: dict[str, list[tuple[int, str]]] = {}
    for source in sources:
        source_headings[source["doi"]] = headings(source)
        heading = source_headings[source["doi"]][0] if source_headings[source["doi"]] else (1, source["title"])
        page, basis = heading
        question = (f"What practice does the paper recommend under ‘{basis}’?"
                    if source_headings[source["doi"]]
                    else f"What are the paper’s main recommendations about ‘{source['title']}’?")
        rows.append(_row(len(rows) + 1, source, "章节事实候选", question, basis, page))

    extra_sources = [source for source in sources if len(source_headings[source["doi"]]) >= 2][:10]
    if len(extra_sources) != 10:
        raise ValueError("Need 10 papers with at least two rule/tip headings to complete the task design")
    for source in extra_sources:
        page, basis = source_headings[source["doi"]][1]
        question = f"What quantified outcome did the paper report after applying or evaluating ‘{basis}’?"
        rows.append(_row(len(rows) + 1, source, "证据边界探测候选", question, basis, page))
    if len(rows) != 40 or len({row["doi"] for row in rows}) != 30:
        raise ValueError("Expected 40 rows across exactly 30 distinct papers")
    return rows


def _row(index: int, source: dict, kind: str, question: str, basis: str, page: int) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    row.update({
        "task_id": f"PT1-H{index:03d}", "paper_split": source["paper_split"],
        "doi": source["doi"], "title": source["title"], "pdf_sha256": source["pdf_sha256"],
        "candidate_type": kind, "candidate_question": question,
        "candidate_basis": basis, "candidate_basis_pdf_page": str(page),
    })
    return row


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = build_rows(manifest)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} unannotated questions across {len({r['doi'] for r in rows})} DOIs: {OUTPUT}")


if __name__ == "__main__":
    main()
