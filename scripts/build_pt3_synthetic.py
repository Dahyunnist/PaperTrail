"""Create immutable synthetic-only PT3 PDFs, gold questions, and hashes."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz


OUT = ROOT / "evals" / "fixtures" / "pt3-synthetic"
GOLD = ROOT / "evals" / "pt3-synthetic-gold-20261023.jsonl"
MANIFEST = ROOT / "evals" / "pt3-synthetic-manifest-20261023.json"


def _write_pdf(path: Path, title: str, columns: tuple[list[str], list[str]], results: list[str]) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((42, 48), title, fontsize=15, fontname="hebo")
    for x, paragraphs in ((48, columns[0]), (315, columns[1])):
        y = 95
        for paragraph in paragraphs:
            is_heading = paragraph in {"Methods", "Eligibility", "Participants", "Assignment"}
            height = 24 if is_heading else 62
            page.insert_textbox(fitz.Rect(x, y, x + 225, y + height), paragraph,
                                fontsize=11 if is_heading else 10, fontname="hebo" if is_heading else "helv",
                                lineheight=1.2)
            y += height + 12
    page = document.new_page()
    page.insert_text((42, 48), f"{title} - Results", fontsize=15, fontname="hebo")
    y = 105
    for paragraph in results:
        page.insert_textbox(fitz.Rect(48, y, 545, y + 54), paragraph, fontsize=11,
                            fontname="helv", lineheight=1.25)
        y += 76
    document.set_metadata({"title": title, "author": "PaperTrail synthetic benchmark"})
    document.save(path, garbage=4, deflate=True)
    document.close()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists() or GOLD.exists() or MANIFEST.exists():
        raise SystemExit("PT3 synthetic fixture already exists; refusing to overwrite frozen evidence")
    OUT.mkdir(parents=True)
    alpha = OUT / "study-alpha.pdf"
    beta = OUT / "study-beta.pdf"
    _write_pdf(alpha, "Synthetic Study Alpha",
               (["Methods", "The trial enrolled 120 adults. Participants were randomized equally: 60 to Alpha care and 60 to usual care.",
                 "The prespecified primary outcome was time from order entry to medicine delivery."],
                ["Eligibility", "Adults with a new medicine order were eligible at two community clinics.",
                 "All participants provided written consent before assignment."]),
               ["In Alpha care, median delivery time was 18 minutes (IQR 12-24).",
                "In usual care, median delivery time was 24 minutes (IQR 16-30)."])
    _write_pdf(beta, "Synthetic Study Beta",
               (["Participants", "The Beta trial enrolled 80 adults, randomized equally: 40 to Beta care and 40 to usual care.",
                 "The primary outcome was time from order entry to medicine delivery."],
                ["Eligibility", "Participants were recruited at one community clinic.",
                 "All participants provided written consent before assignment."]),
               ["In Beta care, median delivery time was 21 minutes (IQR 16-26).",
                "In usual care, median delivery time was 28 minutes (IQR 22-34)."])
    (OUT / "sources.yaml").write_text(
        "version: 1\nroots:\n  - id: pt3_synthetic\n    path: evals/fixtures/pt3-synthetic\n    kinds: [pdf]\n",
        encoding="utf-8",
    )

    shared = lambda file_name: {"root_id": "pt3_synthetic", "file_name": file_name,
                                "sha256": _sha(OUT / file_name)}
    gold = [
        {"id": "pt3-syn-01", "question_type": "fact_location",
         "question": "How many adults did Synthetic Study Alpha enroll?",
         "expected_answer": "120 adults.", "abstain": False,
         "evidence": [{**shared(alpha.name), "pdf_page": 1,
                       "quote": "The trial enrolled 120 adults. Participants were randomized equally: 60 to Alpha care and 60 to usual care."}]},
        {"id": "pt3-syn-02", "question_type": "fact_location",
         "question": "What was Alpha's prespecified primary outcome?",
         "expected_answer": "Time from order entry to medicine delivery.", "abstain": False,
         "evidence": [{**shared(alpha.name), "pdf_page": 1,
                       "quote": "The prespecified primary outcome was time from order entry to medicine delivery."}]},
        {"id": "pt3-syn-03", "question_type": "multi_hop",
         "question": "Compare Alpha care with usual care. What were the absolute and relative reductions in median delivery time, using usual care as the baseline?",
         "expected_answer": "The absolute reduction was 6 minutes. The relative reduction was 25% (6/24).",
         "abstain": False,
         "evidence": [{**shared(alpha.name), "pdf_page": 2,
                       "quote": "In Alpha care, median delivery time was 18 minutes (IQR 12-24)."},
                      {**shared(alpha.name), "pdf_page": 2,
                       "quote": "In usual care, median delivery time was 24 minutes (IQR 16-30)."}]},
        {"id": "pt3-syn-04", "question_type": "cross_paper",
         "question": "Compare the enrollment totals and per-arm allocations in Studies Alpha and Beta.",
         "expected_answer": "Alpha enrolled 120 adults, 60 per arm. Beta enrolled 80 adults, 40 per arm.",
         "abstain": False,
         "evidence": [{**shared(alpha.name), "pdf_page": 1,
                       "quote": "The trial enrolled 120 adults. Participants were randomized equally: 60 to Alpha care and 60 to usual care."},
                      {**shared(beta.name), "pdf_page": 1,
                       "quote": "The Beta trial enrolled 80 adults, randomized equally: 40 to Beta care and 40 to usual care."}]},
        {"id": "pt3-syn-05", "question_type": "multi_hop",
         "question": "Summarize Alpha's enrollment and its reported median follow-up duration.",
         "expected_answer": "Alpha enrolled 120 adults. The evidence does not report a median follow-up duration.",
         "abstain": False,
         "evidence": [{**shared(alpha.name), "pdf_page": 1,
                       "quote": "The trial enrolled 120 adults. Participants were randomized equally: 60 to Alpha care and 60 to usual care."}]},
        {"id": "pt3-syn-06", "question_type": "unanswerable",
         "question": "What attrition rate did Synthetic Study Beta report?",
         "expected_answer": "The frozen evidence contains no attrition rate.", "abstain": True,
         "evidence": []},
    ]
    GOLD.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in gold), encoding="utf-8")
    manifest = {
        "dataset_id": "PT3-synthetic-cross-page-v1-20261023",
        "freeze_date": "2026-10-23",
        "gold_file": GOLD.name,
        "gold_sha256": _sha(GOLD),
        "question_count": len(gold),
        "source_type": "synthetic_only",
        "cloud_evaluation_allowed": True,
        "sources": {path.name: _sha(path) for path in (alpha, beta)},
        "scoring": {"answerability_and_completeness": "manual per-question review against expected_answer and evidence",
                    "citation": "every emitted citation must match source SHA-256, physical page, and exact PDF text",
                    "partial": "supported claims retained; missing requirements must be named",
                    "abstention": "no unsupported fact may be emitted"},
        "limits": ["Two synthetic papers; diagnostic only, not a real-paper generalization benchmark."],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gold": str(GOLD), "questions": len(gold), "manifest_sha256": _sha(MANIFEST)}))


if __name__ == "__main__":
    main()
