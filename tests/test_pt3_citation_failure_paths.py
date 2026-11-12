import hashlib

import fitz

from papertrail.qa import _validate_quote


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
