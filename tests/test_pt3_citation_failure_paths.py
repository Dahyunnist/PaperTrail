import hashlib
import json
from pathlib import Path

import fitz
import yaml

from papertrail.qa import _validate_chunk_quote, _validate_quote, ask
from papertrail.s1_index import index_selection, open_database


def _write_pdf(path, title, quote, extra):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), title)
    page.insert_text((40, 100), quote)
    page.insert_text((40, 130), extra)
    doc.save(path)
    doc.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_matching_quote_on_wrong_source_file_does_not_pass_citation_attribution(tmp_path):
    quote = "Synthetic result reports 42 units after calibration."
    source_a = tmp_path / "source-a.pdf"
    source_b = tmp_path / "source-b.pdf"
    sha_a = _write_pdf(source_a, "Synthetic Study A", quote, "Source A provenance marker.")
    _write_pdf(source_b, "Synthetic Study B", quote, "Source B provenance marker.")

    assert _validate_quote(str(source_a), sha_a, 1, quote, {})
    assert not _validate_quote(str(source_b), sha_a, 1, quote, {})
    assert not _validate_quote(str(source_a), sha_a, 2, quote, {})
    assert not _validate_quote(str(source_a), sha_a, 1, "Synthetic result reports 24 units.", {})


def test_chunk_quote_requires_chunk_page_and_source_to_match(tmp_path):
    quote = "Synthetic result reports 42 units after calibration."
    source = tmp_path / "source.pdf"
    sha = _write_pdf(source, "Synthetic Study", quote, "A separate validation statement supports reproducible review.")
    row = {"text": quote, "path": str(source), "sha256": sha, "pdf_page": 1,
           "text_origin": "native_text", "chunk_id": "synthetic-chunk"}

    assert _validate_chunk_quote(row, quote, {})
    assert not _validate_chunk_quote({**row, "text": "A different indexed chunk."}, quote, {})
    assert not _validate_chunk_quote({**row, "pdf_page": 2}, quote, {})
    assert not _validate_chunk_quote({**row, "pdf_page": True}, quote, {})
    assert not _validate_chunk_quote({**row, "sha256": "0" * 64}, quote, {})
    assert not _validate_chunk_quote({**row, "text_origin": "ocr"}, quote, {})


def test_extractive_qa_cites_its_indexed_chunk_or_explicitly_abstains(tmp_path):
    source_root = tmp_path / "papers"
    source_root.mkdir()
    source = source_root / "synthetic.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 50), "Synthetic Calibration Study", fontsize=18)
    page.insert_text((40, 90), "The quasar assay reports a calibrated synthetic endpoint of 42 units after a reproducible instrument check.", fontsize=10)
    page.insert_text((40, 120), "Researchers recorded the observation on the first physical page and compared it with a separately measured reference cohort.", fontsize=10)
    page.insert_text((40, 150), "The protocol describes sample handling, control selection, data review, and quality checks before reporting the endpoint.", fontsize=10)
    page2 = doc.new_page()
    page2.insert_text((40, 50), "Additional validation details document calibration procedures and independent measurement conditions.", fontsize=10)
    page2.insert_text((40, 80), "The second page records reproducible setup information for the synthetic study and its measurement process.", fontsize=10)
    doc.save(source)
    doc.close()
    sha = hashlib.sha256(source.read_bytes()).hexdigest()

    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "synthetic", "path": str(source_root)}]}), encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({"root_id": "synthetic", "file_name": source.name,
        "relative_path": source.name, "sha256": sha, "kind": "pdf",
        "source_type": "original_pdf"}) + "\n", encoding="utf-8")
    database = tmp_path / "index.sqlite3"
    assert index_selection(database, config, selection)["added"] == 1

    result = ask(database, "What calibrated endpoint does the quasar assay report?",
                 mode="bm25", generate=False)
    assert result["claims"]
    assert result["completion_state"] == "evidence_only"
    for claim in result["claims"]:
        evidence = claim["evidence"]
        assert evidence["sha256"] == sha
        assert evidence["pdf_page"] in (1, 2)
        assert _validate_quote(evidence["path"], sha, evidence["pdf_page"], evidence["quote"], {})
        conn = open_database(database, readonly=True)
        try:
            indexed = conn.execute(
                "SELECT c.page_number,c.body,v.sha256,l.absolute_path "
                "FROM chunks c JOIN paper_versions v USING(version_id) "
                "JOIN source_locations l USING(version_id) WHERE c.chunk_id=?",
                (evidence["chunk_id"],)).fetchone()
        finally:
            conn.close()
        assert indexed
        assert indexed["sha256"] == evidence["sha256"]
        assert indexed["page_number"] == evidence["pdf_page"]
        assert indexed["absolute_path"] == evidence["path"]
        assert " ".join(evidence["quote"].casefold().split()) in " ".join(indexed["body"].casefold().split())

    missing = ask(database, "What serial number is recorded?", mode="bm25", generate=False)
    assert missing["status"] == "abstained"
    assert missing["completion_state"] == "no_evidence"
    assert missing["claims"] == []
