from pathlib import Path
import shutil

import fitz

from papertrail.audit import discover, duplicate_groups, excluded, normalize_title


def _make_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 40), "This synthetic fixture has enough ordinary words to be counted as a text page.")
    page.insert_text((40, 80), "Column A       Column B       Column C")
    for i in range(8):
        page.insert_text((40, 100 + i * 14), f"row {i}       value {i}       result {i}")
    doc.save(path)
    doc.close()


def test_title_normalization_and_exclusion_are_case_insensitive():
    assert normalize_title("  Café—DATA  ") == "café data"
    assert excluded(Path("E:/papers/Reports/figures/p1.pdf"), ["reports", "figures"])
    assert not excluded(Path("E:/papers/p1.pdf"), ["reports", "figures"])


def test_discovery_counts_duplicates_and_applies_exclusions(tmp_path):
    first = tmp_path / "root1" / "paper.pdf"
    duplicate = tmp_path / "root2" / "copy.pdf"
    _make_pdf(first)
    duplicate.parent.mkdir(parents=True)
    shutil.copyfile(first, duplicate)
    _make_pdf(tmp_path / "root1" / "reports" / "ignored.pdf")
    (tmp_path / "root1" / "notes.md").write_text("# Note\nshort note", encoding="utf-8")
    config = {
        "roots": [
            {"id": "a", "path": str(tmp_path / "root1"), "kinds": ["pdf", "md"]},
            {"id": "b", "path": str(tmp_path / "root2"), "kinds": ["pdf"]},
        ],
        "bibliography": [],
        "exclude_path_segments": ["reports"],
    }
    rows, issues = discover(config)
    pdfs = [row for row in rows if row["kind"] == "pdf"]
    exact, _ = duplicate_groups(rows)
    assert not issues
    assert len(pdfs) == 2
    assert len(exact) == 1
    assert all(row["parseable_page_ratio"] == 1.0 for row in pdfs)
    assert all(row["table_dense_pages"] == [1] for row in pdfs)
    assert sum(row["kind"] == "md" for row in rows) == 1
