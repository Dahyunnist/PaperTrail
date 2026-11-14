import csv
import hashlib
import json
import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import import_pt1_human_csv as csv_importer
import import_pt1_gold_jsonl as jsonl_importer
import validate_pt1_gold_jsonl as jsonl_validator
from papertrail.gold import load_gold, verify_quotes
from papertrail.evaluate_run import run_evaluation
from papertrail.s1_index import index_selection

FIELDS = [
    "task_id", "paper_split", "doi", "title", "pdf_sha256", "candidate_type", "candidate_question",
    "candidate_basis", "candidate_basis_pdf_page", "question_type", "answerability", "expected_answer",
    "minimal_complete_evidence_quote", "evidence_pdf_pages", "original_pdf_excerpt", "span_start_char",
    "span_end_char", "annotator", "reviewer", "review_status", "notes",
]


def _pdf(path: Path, text: str) -> tuple[str, int]:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    with pymupdf.open(path) as document:
        extracted = document[0].get_text("text")
    return hashlib.sha256(path.read_bytes()).hexdigest(), extracted.index(text)


def _fixture(tmp_path, monkeypatch):
    source_defs = [
        ("10.1234/answered", "The trial enrolled 12 participants."),
        ("10.1234/refusal", "No ten-year follow-up was reported."),
    ]
    manifest_sources = []
    rows = []
    for index, (doi, text) in enumerate(source_defs, 1):
        filename = f"paper-{index}.pdf"
        digest, start = _pdf(tmp_path / filename, text)
        manifest_sources.append({"doi": doi, "local_pdf": filename, "pdf_sha256": digest})
        answerable = index == 1
        rows.append({
            "task_id": f"PT1-H{index:03}", "paper_split": "development_seen", "doi": doi,
            "title": f"Fixture {index}", "pdf_sha256": digest, "candidate_type": "章节事实候选",
            "candidate_question": "How many participants were enrolled?" if answerable else "Was a ten-year follow-up reported?",
            "candidate_basis": "fixture basis", "candidate_basis_pdf_page": "1",
            "question_type": "fact_location" if answerable else "unanswerable",
            "answerability": "可答" if answerable else "不可答",
            "expected_answer": "The trial enrolled 12 participants." if answerable else "Cannot answer: no ten-year follow-up is reported.",
            "minimal_complete_evidence_quote": text if answerable else "",
            "evidence_pdf_pages": "1" if answerable else "",
            "original_pdf_excerpt": text if answerable else "",
            "span_start_char": str(start) if answerable else "", "span_end_char": str(start + len(text)) if answerable else "",
            "annotator": "human-a", "reviewer": "human-b", "review_status": "通过", "notes": "",
        })
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"sources": manifest_sources}), encoding="utf-8")
    csv_path = tmp_path / "annotated.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(jsonl_validator, "ROOT", tmp_path)
    monkeypatch.setattr(jsonl_importer, "ROOT", tmp_path)
    return csv_path, manifest_path


def test_csv_command_path_exports_v2_and_imports_runtime_gold(tmp_path, monkeypatch):
    csv_path, manifest = _fixture(tmp_path, monkeypatch)
    output_v2 = tmp_path / "out" / "human-v2.jsonl"
    output_gold = tmp_path / "out" / "runtime-gold.jsonl"
    output_sources = tmp_path / "out" / "runtime-sources.yaml"

    question_count, quote_count = csv_importer.import_csv(
        csv_path, output_v2, output_gold, output_sources, manifest, min_questions=2, min_papers=2)

    v2 = [json.loads(line) for line in output_v2.read_text(encoding="utf-8").splitlines()]
    runtime = load_gold(output_gold, minimum_questions=2)
    assert question_count == 2 and quote_count == 1
    assert [row["answerability"] for row in v2] == ["answerable", "unanswerable"]
    assert [row["question_type"] for row in v2] == ["fact_location", "unanswerable"]
    assert [row["abstain"] for row in runtime] == [False, True]
    assert verify_quotes(runtime, output_sources) == 1


def test_imported_synthetic_csv_runs_deterministic_report(tmp_path, monkeypatch):
    csv_path, source_manifest = _fixture(tmp_path, monkeypatch)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["candidate_question"] = "trial enrolled 12 participants"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    output = tmp_path / "converted"
    runtime_gold = output / "runtime-gold.jsonl"
    runtime_sources = output / "runtime-sources.yaml"
    csv_importer.import_csv(csv_path, output / "reviewed-v2.jsonl", runtime_gold,
                             runtime_sources, source_manifest, min_questions=2, min_papers=2)

    source_rows = json.loads(source_manifest.read_text(encoding="utf-8"))["sources"]
    selection = tmp_path / "selection.jsonl"
    selection.write_text("".join(
        json.dumps({
            "root_id": "pt1-" + hashlib.sha256(source["doi"].encode("utf-8")).hexdigest()[:12],
            "file_name": source["local_pdf"], "relative_path": source["local_pdf"],
            "sha256": source["pdf_sha256"], "kind": "pdf", "source_type": "original_pdf",
        }) + "\n" for source in source_rows
    ), encoding="utf-8")
    database = tmp_path / "index.sqlite3"
    index_selection(database, runtime_sources, selection)

    manifest = output / "evaluation-manifest.json"
    manifest.write_text(json.dumps({
        "dataset_id": "synthetic-csv-runner-test", "split": "development",
        "source_type": "synthetic_only", "gold_source": "synthetic_fixture",
        "gold_file": runtime_gold.name,
        "gold_sha256": hashlib.sha256(runtime_gold.read_bytes()).hexdigest(),
        "question_count": 2,
    }), encoding="utf-8")
    report = run_evaluation(database, runtime_gold, manifest, output / "report.json",
                            k=1, modes=("bm25",), minimum_questions=2)
    assert report["evaluation"]["answerable_questions"] == 1
    assert report["evaluation"]["unanswerable_questions"] == 1
    assert report["run_manifest"]["gold_source"] == "synthetic_fixture"


def test_csv_import_cli_runs_all_steps_with_one_command(tmp_path, monkeypatch, capsys):
    csv_path, manifest = _fixture(tmp_path, monkeypatch)
    output_v2 = tmp_path / "out" / "human-v2.jsonl"
    output_gold = tmp_path / "out" / "runtime-gold.jsonl"
    output_sources = tmp_path / "out" / "runtime-sources.yaml"
    monkeypatch.setattr(sys, "argv", [
        "import_pt1_human_csv.py", str(csv_path), "--manifest", str(manifest),
        "--output-v2", str(output_v2), "--output-gold", str(output_gold),
        "--output-sources", str(output_sources), "--min-questions", "2", "--min-papers", "2",
    ])

    csv_importer.main()

    assert "Imported 2 reviewed annotations; verified 1 PDF quotes." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("review_status", "", "review_status must be 通过"),
     ("reviewer", "human-a", "annotator and reviewer must be present and different"),
     ("answerability", "歧义", "resolve 歧义 before export"),
     ("minimal_complete_evidence_quote", "", "minimal_complete_evidence_quote is required"),
     ("pdf_sha256", "0" * 64, "PDF SHA-256 does not match")],
)
def test_csv_import_rejects_incomplete_review_or_bad_source(tmp_path, monkeypatch, field, value, message):
    csv_path, manifest = _fixture(tmp_path, monkeypatch)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    rows[0][field] = value
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    output_v2 = tmp_path / "out" / "human-v2.jsonl"
    output_gold = tmp_path / "out" / "runtime-gold.jsonl"
    output_sources = tmp_path / "out" / "runtime-sources.yaml"

    with pytest.raises(ValueError, match=message):
        csv_importer.import_csv(csv_path, output_v2, output_gold, output_sources, manifest,
                                min_questions=2, min_papers=2)

    assert not output_v2.exists()
    assert not output_gold.exists()
    assert not output_sources.exists()


def test_csv_import_rejects_nonmatching_page_span(tmp_path, monkeypatch):
    csv_path, manifest = _fixture(tmp_path, monkeypatch)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    rows[0]["span_start_char"] = "1"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="quote span does not exactly match"):
        csv_importer.export_csv_rows(csv_path, manifest)


@pytest.mark.parametrize("filename", ["paper-1.pdf", "paper-2.pdf"])
def test_csv_import_rejects_source_pdf_changed_after_manifest_freeze(tmp_path, monkeypatch, filename):
    csv_path, manifest = _fixture(tmp_path, monkeypatch)
    source = tmp_path / filename
    source.write_bytes(source.read_bytes() + b" changed after freeze")

    with pytest.raises(ValueError, match="local PDF SHA-256 does not match the frozen manifest"):
        csv_importer.export_csv_rows(csv_path, manifest)
