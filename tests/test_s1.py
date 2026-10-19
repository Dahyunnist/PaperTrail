import json
import shutil
from pathlib import Path

import fitz
import yaml

from papertrail.audit import _hash
from papertrail.s1_index import _title_from_pdf, database_summary, index_selection, inspect_document, search


def _pdf(path: Path, second_page: str = "latepagekeyword appears on the second physical page.") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 50), "Synthetic Benchmark Paper", fontsize=18)
    page.insert_text((40, 84), "1 Introduction", fontsize=14)
    page.insert_text((40, 110), "DOI: 10.4242/test.1234", fontsize=10)
    page.insert_text((40, 135), "CTGAN evaluates mixed continuous and discrete columns with enough words for reliable text-page classification.", fontsize=10)
    page.insert_text((40, 170), "Dataset       Metric       Score", fontsize=10)
    page.insert_text((40, 188), "Adult          AUC           0.91", fontsize=10)
    next_page = doc.new_page()
    next_page.insert_text((40, 50), second_page + " The held-out page records a separate observation for physical page verification.", fontsize=10)
    doc.set_metadata({"title": "Synthetic Benchmark Paper"})
    doc.save(path)
    doc.close()


def test_s1_indexes_text_pages_notes_versions_and_exact_duplicates(tmp_path):
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    original = root_a / "paper.pdf"
    duplicate = root_b / "paper-copy.pdf"
    version = root_b / "paper-revision.pdf"
    note = root_a / "paper-note.md"
    _pdf(original)
    root_b.mkdir(parents=True)
    shutil.copyfile(original, duplicate)
    _pdf(version, "revisedversionmarker appears on the second physical page.")
    note.write_text(
        "# Synthetic Benchmark Paper\n\n## Personal reading note\n\nMy note says CTGAN is a reading clue, not original paper evidence.\n",
        encoding="utf-8",
    )
    sources = tmp_path / "sources.yaml"
    sources.write_text(yaml.safe_dump({"roots": [
        {"id": "a", "path": str(root_a), "kinds": ["pdf", "md"]},
        {"id": "b", "path": str(root_b), "kinds": ["pdf"]},
    ]}, allow_unicode=True), encoding="utf-8")
    selected = [
        {"root_id": "a", "file_name": original.name, "sha256": _hash(original), "kind": "pdf", "source_type": "original_pdf"},
        {"root_id": "b", "file_name": duplicate.name, "sha256": _hash(duplicate), "kind": "pdf", "source_type": "original_pdf"},
        {"root_id": "b", "file_name": version.name, "sha256": _hash(version), "kind": "pdf", "source_type": "original_pdf"},
        {"root_id": "a", "file_name": note.name, "sha256": _hash(note), "kind": "md", "source_type": "reading_note"},
    ]
    manifest = tmp_path / "selection.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in selected), encoding="utf-8")
    db = tmp_path / "local" / "papertrail.sqlite3"

    first = index_selection(db, sources, manifest)
    assert first["added"] == 3
    assert first["duplicates"] == 1
    assert first["issues"] == []
    summary = database_summary(db)
    assert summary == {"documents": 3, "chunks": 15, "reading_notes": 1, "source_locations": 4}

    # A query may find useful note text, but callers can request original-paper sources only.
    notes = search(db, "reading clue", limit=5, source_type="reading_note")
    originals = search(db, "CTGAN", limit=5, source_type="original_pdf")
    assert notes and all(hit["source_type"] == "reading_note" and hit["pdf_page"] is None for hit in notes)
    assert originals and all(hit["source_type"] == "original_pdf" for hit in originals)

    page_hits = search(db, "latepagekeyword", limit=5, source_type="original_pdf")
    assert page_hits and page_hits[0]["pdf_page"] == 2
    doi_hits = search(db, "10.4242/test.1234", limit=5, source_type="original_pdf")
    assert doi_hits and doi_hits[0]["pdf_page"] == 1
    assert "AUC" in search(db, "AUC", limit=5)[0]["text"]

    inspection = inspect_document(db, _hash(original)[:16])
    assert inspection is not None
    assert inspection["page_count"] == 2
    assert len(inspection["locations"]) == 2
    assert inspection["identity_status"] == "provisional"
    assert inspection["parse_status"] == "text"


def test_pdf_title_ignores_publisher_banner():
    path = Path("fallback-paper.pdf")
    title = _title_from_pdf(path, {"title": "Published as a conference paper at ICLR 2026"},
                            "Published as a conference paper at ICLR 2026\n\nA Useful Scientific Paper Title\n")
    assert title == "A Useful Scientific Paper Title"
