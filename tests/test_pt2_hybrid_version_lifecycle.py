import hashlib
import json
from pathlib import Path

import fitz
import yaml

from papertrail.retrieval import retrieve
from papertrail.s1_index import index_selection


def _make_pdf(path: Path, marker: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 50), "Synthetic Benchmark Paper", fontsize=18)
    page.insert_text((40, 84), "1 Introduction", fontsize=14)
    page.insert_text((40, 110), "DOI: 10.4242/test.1234", fontsize=10)
    page.insert_text((40, 135), "CTGAN evaluates mixed continuous and discrete columns with enough words for reliable text-page classification.", fontsize=10)
    page.insert_text((40, 170), "Dataset       Metric       Score", fontsize=10)
    page.insert_text((40, 188), "Adult          AUC           0.91", fontsize=10)
    page = doc.new_page()
    page.insert_text((40, 50), f"{marker} is on the second page with enough words for indexing and reproducible synthetic evaluation.", fontsize=10)
    doc.save(path)
    doc.close()


def _selection(path: Path, root: Path, manifest: Path) -> None:
    if not path.exists():
        manifest.write_text("", encoding="utf-8")
        return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps({
        "root_id": "synthetic", "file_name": path.name, "relative_path": path.name,
        "sha256": digest, "kind": "pdf", "source_type": "original_pdf",
    }) + "\n", encoding="utf-8")


def _find(db: Path, artifact: Path, query: str, mode: str) -> list[dict]:
    return retrieve(db, query, limit=10, source_type="original_pdf", mode=mode, artifact=artifact)


def test_hybrid_retrieval_tracks_synthetic_version_update_and_delete(tmp_path):
    root = tmp_path / "papers"
    root.mkdir()
    source = root / "paper.pdf"
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "synthetic", "path": str(root)}]}), encoding="utf-8")
    manifest = tmp_path / "selection.jsonl"
    db = tmp_path / "index.sqlite3"
    artifact = tmp_path / "vectors.joblib"

    _make_pdf(source, "oldquartzmarker")
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    _selection(source, root, manifest)
    assert index_selection(db, config, manifest, reconcile=True)["added"] == 1
    for mode in ("bm25", "vector", "hybrid"):
        assert _find(db, artifact, "oldquartzmarker", mode)

    _make_pdf(source, "newcobaltmarker")
    new_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    _selection(source, root, manifest)
    assert index_selection(db, config, manifest, reconcile=True)["added"] == 1
    for mode in ("bm25", "vector", "hybrid"):
        assert _find(db, artifact, "newcobaltmarker", mode)
        assert all(row["sha256"] != old_hash for row in _find(db, artifact, "oldquartzmarker", mode))
        assert all(row["sha256"] == new_hash for row in _find(db, artifact, "newcobaltmarker", mode))

    source.unlink()
    manifest.write_text("", encoding="utf-8")
    assert index_selection(db, config, manifest, reconcile=True)["added"] == 0
    for mode in ("bm25", "vector", "hybrid"):
        assert _find(db, artifact, "newcobaltmarker", mode) == []
