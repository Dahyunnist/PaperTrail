"""Recheck hashes, pages, and exact native-text citations in synthetic PT3 output."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz

from papertrail.gold import _normalize_excerpt


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "reports/pt3-synthetic-model-20261023.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "evals/pt3-synthetic-manifest-20261023.json")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if report.get("gold_sha256") != manifest["gold_sha256"]:
        raise SystemExit("报告的黄金集哈希与冻结清单不匹配")
    if report.get("source_sha256") != manifest["sources"]:
        raise SystemExit("报告的来源哈希与冻结清单不匹配")

    checked = 0
    for case in report["cases"]:
        for claim in case.get("claims", []):
            for pointer in claim.get("support_evidence", []):
                name = Path(pointer["path"]).name
                source = ROOT / "evals/fixtures/pt3-synthetic" / name
                if (manifest["sources"].get(name) != pointer.get("sha256")
                        or not source.is_file() or _sha256(source) != pointer["sha256"]):
                    raise SystemExit(f"{case['id']}: 引文源哈希不匹配")
                if pointer.get("text_origin") != "native_text":
                    raise SystemExit(f"{case['id']}: OCR 派生文本不得成为引文")
                with fitz.open(source) as document:
                    page = pointer.get("pdf_page")
                    if not isinstance(page, int) or not 1 <= page <= document.page_count:
                        raise SystemExit(f"{case['id']}: PDF 页码无效")
                    page_text = _normalize_excerpt(document[page - 1].get_text("text"))
                    if _normalize_excerpt(pointer.get("quote", "")) not in page_text:
                        raise SystemExit(f"{case['id']}: 引文不在所标 PDF 页")
                checked += 1
    print(json.dumps({"cases": len(report["cases"]), "claims": sum(
        len(case.get("claims", [])) for case in report["cases"]),
        "native_text_citations_verified": checked, "invalid": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
