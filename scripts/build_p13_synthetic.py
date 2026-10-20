"""Build deterministic multi-document synthetic PDFs and the P13 RAG holdout."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import fitz
import yaml

from papertrail.gold import load_gold, verify_quotes
from papertrail.s1_index import index_selection

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "evals" / "p13-synthetic"
GOLD_PATH = ROOT / "evals" / "p13-synthetic-gold.jsonl"
MANIFEST_PATH = ROOT / "evals" / "p13-synthetic-manifest.json"
LOCAL_DIR = ROOT / ".local" / "p13-synthetic"

DOCUMENTS = {
    "study-a.pdf": (
        "Synthetic Parcel Delivery Pilot",
        [
            "The pilot tracked 240 synthetic deliveries over twelve days.",
            "Median scan-to-door time was 18 minutes across all 240 deliveries.",
            "Urban deliveries included 160 parcels and had a median scan-to-door time of 14 minutes.",
            "Rural deliveries included 80 parcels and had a median scan-to-door time of 26 minutes.",
            "No individual customer addresses or driver identifiers were stored.",
        ],
    ),
    "study-b.pdf": (
        "Synthetic Cold-Chain Container Trial",
        [
            "Two cold-chain container designs were each tested on 80 synthetic shipments.",
            "Insulated Container A failed temperature control in 2.5 percent of shipments.",
            "Foam Container B failed temperature control in 6.25 percent of shipments.",
            "The temperature-control threshold was 8 degrees Celsius.",
            "A failure meant a reading above the threshold for more than 10 consecutive minutes.",
        ],
    ),
    "study-c.pdf": (
        "Synthetic Depot Route Policy Simulation",
        [
            "Policy Cedar reduced mean depot waiting time from 12 minutes to 9 minutes in a simulation of 60 routes.",
            "The same simulation estimated fuel consumption fell from 4.2 to 3.9 liters per route.",
            "The authors reported descriptive estimates and conducted no significance test.",
            "Driver names were not collected.",
        ],
    ),
    "study-d.pdf": (
        "Synthetic Dispatch Intervention Trial",
        [
            "The dispatch intervention group included 100 synthetic orders, and the control group included 100 orders.",
            "Successful delivery rates were 92 percent in the intervention group and 89 percent in the control group.",
            "Mean scan-to-door times were 17 minutes for the intervention group and 18.5 minutes for the control group.",
            "The reported confidence interval crossed zero, so the authors did not establish a statistically reliable improvement.",
            "The report did not break outcomes down by city or weather conditions.",
        ],
    ),
}

# Questions and answers are authored independently from model output. Each evidence
# quote is checked against the generated PDF, page number, and frozen document hash.
GOLD = [
    ("P13-01", "fact_location", "What was the overall median scan-to-door time, and how many deliveries were included?", "The overall median was 18 minutes across 240 deliveries.", [("study-a.pdf", "Median scan-to-door time was 18 minutes across all 240 deliveries.")]),
    ("P13-02", "fact_location", "How many urban parcels were tracked, and what was their median scan-to-door time?", "There were 160 urban parcels, with a median of 14 minutes.", [("study-a.pdf", "Urban deliveries included 160 parcels and had a median scan-to-door time of 14 minutes.")]),
    ("P13-03", "fact_location", "Report the rural delivery count and median scan-to-door time.", "There were 80 rural parcels, with a median of 26 minutes.", [("study-a.pdf", "Rural deliveries included 80 parcels and had a median scan-to-door time of 26 minutes.")]),
    ("P13-04", "multi_hop", "By how many minutes did the rural median exceed the urban median? Include both source values.", "Rural deliveries were 12 minutes slower by median: 26 minutes versus 14 minutes.", [("study-a.pdf", "Urban deliveries included 160 parcels and had a median scan-to-door time of 14 minutes."), ("study-a.pdf", "Rural deliveries included 80 parcels and had a median scan-to-door time of 26 minutes.")]),
    ("P13-05", "fact_location", "Did the delivery pilot store individual customer addresses or driver identifiers?", "No. It stored neither individual customer addresses nor driver identifiers.", [("study-a.pdf", "No individual customer addresses or driver identifiers were stored.")]),
    ("P13-06", "fact_location", "How many shipments were used for each cold-chain container design?", "Each design was tested on 80 shipments.", [("study-b.pdf", "Two cold-chain container designs were each tested on 80 synthetic shipments.")]),
    ("P13-07", "fact_location", "What was the temperature-control failure rate for Insulated Container A?", "Insulated Container A had a 2.5 percent failure rate.", [("study-b.pdf", "Insulated Container A failed temperature control in 2.5 percent of shipments.")]),
    ("P13-08", "fact_location", "What failure rate did Foam Container B record?", "Foam Container B had a 6.25 percent failure rate.", [("study-b.pdf", "Foam Container B failed temperature control in 6.25 percent of shipments.")]),
    ("P13-09", "multi_hop", "How many percentage points lower was Container A's failure rate than Container B's?", "Container A's rate was 3.75 percentage points lower: 2.5 percent versus 6.25 percent.", [("study-b.pdf", "Insulated Container A failed temperature control in 2.5 percent of shipments."), ("study-b.pdf", "Foam Container B failed temperature control in 6.25 percent of shipments.")]),
    ("P13-10", "fact_location", "What temperature threshold defined the cold-chain control limit?", "The threshold was 8 degrees Celsius.", [("study-b.pdf", "The temperature-control threshold was 8 degrees Celsius.")]),
    ("P13-11", "fact_location", "What exact condition counted as a temperature-control failure?", "A reading above 8 degrees Celsius for more than 10 consecutive minutes counted as a failure.", [("study-b.pdf", "A failure meant a reading above the threshold for more than 10 consecutive minutes.")]),
    ("P13-12", "fact_location", "How did Policy Cedar change mean depot waiting time?", "It reduced mean waiting time from 12 minutes to 9 minutes.", [("study-c.pdf", "Policy Cedar reduced mean depot waiting time from 12 minutes to 9 minutes in a simulation of 60 routes.")]),
    ("P13-13", "fact_location", "How many routes were in the Cedar policy simulation?", "The simulation included 60 routes.", [("study-c.pdf", "Policy Cedar reduced mean depot waiting time from 12 minutes to 9 minutes in a simulation of 60 routes.")]),
    ("P13-14", "fact_location", "What fuel consumption change did the Cedar simulation estimate per route?", "It estimated a decrease from 4.2 to 3.9 liters per route.", [("study-c.pdf", "The same simulation estimated fuel consumption fell from 4.2 to 3.9 liters per route.")]),
    ("P13-15", "multi_hop", "What percent decrease from baseline does the fuel estimate represent? Show the baseline and new value.", "The estimate is about a 7.1 percent decrease, from 4.2 to 3.9 liters per route.", [("study-c.pdf", "The same simulation estimated fuel consumption fell from 4.2 to 3.9 liters per route.")]),
    ("P13-16", "fact_location", "Did the route-policy authors perform a statistical significance test?", "No. They reported descriptive estimates and conducted no significance test.", [("study-c.pdf", "The authors reported descriptive estimates and conducted no significance test.")]),
    ("P13-17", "fact_location", "Were driver names collected in the route-policy simulation?", "No. Driver names were not collected.", [("study-c.pdf", "Driver names were not collected.")]),
    ("P13-18", "fact_location", "What were the successful-delivery rates and sample sizes for intervention and control?", "Each group had 100 orders; success was 92 percent for intervention and 89 percent for control.", [("study-d.pdf", "The dispatch intervention group included 100 synthetic orders, and the control group included 100 orders."), ("study-d.pdf", "Successful delivery rates were 92 percent in the intervention group and 89 percent in the control group.")]),
    ("P13-19", "fact_location", "Compare mean scan-to-door time for the dispatch intervention and control groups.", "The intervention mean was 17 minutes; the control mean was 18.5 minutes.", [("study-d.pdf", "Mean scan-to-door times were 17 minutes for the intervention group and 18.5 minutes for the control group.")]),
    ("P13-20", "fact_location", "Was the dispatch intervention shown to produce a statistically reliable improvement?", "No. The confidence interval crossed zero, so a statistically reliable improvement was not established.", [("study-d.pdf", "The reported confidence interval crossed zero, so the authors did not establish a statistically reliable improvement.")]),
    ("P13-21", "cross_paper", "Compare Study A's overall scan-to-door median with Study C's depot waiting-time change. Are these the same measure?", "Study A reports an 18-minute scan-to-door median. Study C reports depot waiting falling from 12 to 9 minutes. They are different measures.", [("study-a.pdf", "Median scan-to-door time was 18 minutes across all 240 deliveries."), ("study-c.pdf", "Policy Cedar reduced mean depot waiting time from 12 minutes to 9 minutes in a simulation of 60 routes.")]),
    ("P13-22", "cross_paper", "Compare the shipment sample size in Study B with the route sample size in Study C.", "Each container design in Study B used 80 shipments; Study C used 60 routes.", [("study-b.pdf", "Two cold-chain container designs were each tested on 80 synthetic shipments."), ("study-c.pdf", "Policy Cedar reduced mean depot waiting time from 12 minutes to 9 minutes in a simulation of 60 routes.")]),
    ("P13-23", "unanswerable", "Which city had the longest delivery time in Study A?", "The study compares urban and rural deliveries but does not name cities.", []),
    ("P13-24", "unanswerable", "Which individual driver performed best under Policy Cedar?", "The report does not provide driver-level results, and driver names were not collected.", []),
    ("P13-25", "unanswerable", "How much money did Policy Cedar save in operating costs?", "The route-policy report gives no operating-cost or monetary-savings figure.", []),
    ("P13-26", "unanswerable", "Which weather condition caused the most dispatch delays?", "The dispatch report does not provide weather breakdowns.", []),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_pdfs() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, (title, paragraphs) in DOCUMENTS.items():
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((54, 60), title, fontsize=16, fontname="helv")
        page.insert_textbox(fitz.Rect(54, 95, 558, 730), "\n\n".join(paragraphs),
                            fontsize=11, lineheight=1.3, fontname="helv")
        doc.set_metadata({"title": title, "author": "PaperTrail Synthetic Benchmark",
                          "creationDate": "D:20261020000000Z", "modDate": "D:20261020000000Z"})
        target = FIXTURE_DIR / name
        doc.save(target, garbage=4, deflate=True, no_new_id=True)
        doc.close()


def main() -> None:
    _write_pdfs()
    source_root = LOCAL_DIR / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    selections = []
    document_hashes = {}
    for name in sorted(DOCUMENTS):
        source = FIXTURE_DIR / name
        destination = source_root / name
        shutil.copyfile(source, destination)
        digest = _sha256(source)
        document_hashes[name] = digest
        selections.append({"root_id": "p13-fixture", "file_name": name, "relative_path": name,
                           "sha256": digest, "kind": "pdf", "source_type": "original_pdf"})

    gold_rows = []
    for item_id, kind, question, answer, refs in GOLD:
        evidence = [{"root_id": "p13-fixture", "file_name": name, "sha256": document_hashes[name],
                     "pdf_page": 1, "quote": quote} for name, quote in refs]
        gold_rows.append({"id": item_id, "question_type": kind, "question": question,
                          "expected_answer": answer, "abstain": kind == "unanswerable", "evidence": evidence})
    GOLD_PATH.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in gold_rows), encoding="utf-8")

    sources_path = LOCAL_DIR / "sources.yaml"
    sources_path.write_text(yaml.safe_dump({"roots": [{"id": "p13-fixture", "path": str(source_root),
                                                         "kinds": ["pdf"]}]}, allow_unicode=True), encoding="utf-8")
    selection_path = LOCAL_DIR / "selection.jsonl"
    selection_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selections), encoding="utf-8")
    database = LOCAL_DIR / "papertrail.sqlite3"
    for path in (database, database.with_name(database.name + "-wal"), database.with_name(database.name + "-shm")):
        path.unlink(missing_ok=True)
    indexed = index_selection(database, sources_path, selection_path)

    items = load_gold(GOLD_PATH, minimum_questions=26)
    verified = verify_quotes(items, sources_path)
    earlier_questions = set()
    for path in ROOT.glob("evals/*gold*.jsonl"):
        if path == GOLD_PATH:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                earlier_questions.add(" ".join(json.loads(line)["question"].casefold().split()))
    current_questions = {" ".join(item["question"].casefold().split()) for item in items}
    overlap = current_questions & earlier_questions
    manifest = {
        "benchmark": "PaperTrail P13 synthetic multi-document RAG holdout",
        "data_policy": "synthetic fixtures only; no local thesis material",
        "question_count": len(items),
        "answerable_count": sum(not item["abstain"] for item in items),
        "unanswerable_count": sum(item["abstain"] for item in items),
        "documents": document_hashes,
        "gold_sha256": _sha256(GOLD_PATH),
        "verified_evidence_quotes": verified,
        "indexed_chunks": indexed["chunks"],
        "exact_overlap_with_earlier_gold_count": len(overlap),
        "scope": "Single 26-question English synthetic holdout across four one-page PDFs; not production evidence.",
    }
    if overlap:
        raise ValueError("P13 contains an exact normalized question overlap with an earlier benchmark")
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"questions={len(items)} evidence_quotes_verified={verified} documents={len(document_hashes)} "
          f"chunks={indexed['chunks']} exact_question_overlap={len(overlap)}")


if __name__ == "__main__":
    main()
