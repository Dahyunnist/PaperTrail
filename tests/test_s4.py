import json
from pathlib import Path

import fitz
import yaml

from papertrail.audit import _hash
from papertrail.compare import add_gap_candidate, compare_papers, comparison_report, label_evidence
from papertrail.s1_index import index_selection


def _paper(path: Path, title: str, sentence: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), title, fontsize=16)
    page.insert_text((40, 100), sentence, fontsize=11)
    doc.set_metadata({"title": title})
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()


def test_cross_paper_evidence_stays_unclassified_until_user_labels(tmp_path):
    root = tmp_path / "corpus"
    a, b = root / "paper-a.pdf", root / "paper-b.pdf"
    _paper(a, "Categorical Diffusion Paper A",
           "The method adds multinomial noise for categorical variables and Gaussian noise for continuous variables.")
    _paper(b, "Categorical Diffusion Paper B",
           "The method does not use categorical noise; it represents every feature as a continuous variable.")
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "papers", "path": str(root)}]}), encoding="utf-8")
    manifest = tmp_path / "selection.jsonl"
    manifest.write_text("".join(json.dumps({"root_id": "papers", "file_name": path.name,
        "relative_path": path.name, "sha256": _hash(path), "kind": "pdf", "source_type": "original_pdf"}) + "\n"
        for path in (a, b)), encoding="utf-8")
    db = tmp_path / "local" / "papers.sqlite3"
    assert index_selection(db, config, manifest)["added"] == 2

    result = compare_papers(db, "categorical diffusion", "uses multinomial noise for categorical variables", 4)
    assert result["paper_count"] == 2
    assert all(item["label"] == "unclassified" for item in result["evidence"])
    assert {item["sha256"] for item in result["evidence"]} == {_hash(a), _hash(b)}
    evidence = result["evidence"]
    label_evidence(db, evidence[0]["evidence_id"], "supports", "Matches the claim's described method.")
    label_evidence(db, evidence[1]["evidence_id"], "contradicts", "The paper describes a different treatment.")
    add_gap_candidate(db, result["comparison_id"],
                      "The pilot contains no direct comparison of the two noise processes.",
                      [evidence[0]["evidence_id"], evidence[1]["evidence_id"]])
    report = comparison_report(db, result["comparison_id"])
    assert report["stance_summary"]["supports"] == 1
    assert report["stance_summary"]["contradicts"] == 1
    assert report["gap_candidates"][0]["status"] == "user_proposed"
