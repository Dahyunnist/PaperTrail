"""Validate S0 gold-set structure and short evidence pointers against sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import yaml

QUESTION_TYPES = {"fact_location", "method_comparison", "cross_paper", "multi_hop", "conflict", "unanswerable"}
REQUIRED = {"id", "question_type", "question", "expected_answer", "abstain", "evidence"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_excerpt(text: str) -> str:
    # PyMuPDF may split a word at a printed line break; normalize ligatures as well.
    text = unicodedata.normalize("NFKC", text.replace("-\n", ""))
    return " ".join(text.split()).casefold()


def load_gold(path: Path) -> list[dict[str, Any]]:
    items = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"gold.jsonl 第 {line_number} 行不是有效 JSON: {exc}") from exc
        if not isinstance(item, dict) or not REQUIRED.issubset(item):
            raise ValueError(f"gold.jsonl 第 {line_number} 行缺少必需字段")
        if item["question_type"] not in QUESTION_TYPES:
            raise ValueError(f"{item['id']}: 未知 question_type")
        if not item["question"].strip() or not item["expected_answer"].strip():
            raise ValueError(f"{item['id']}: question/expected_answer 不能为空")
        if item["abstain"] != (item["question_type"] == "unanswerable"):
            raise ValueError(f"{item['id']}: abstain 必须与 unanswerable 类别一致")
        if item["abstain"] and item["evidence"]:
            raise ValueError(f"{item['id']}: 不可回答题不能附上支持性原文證據")
        if not item["abstain"] and not item["evidence"]:
            raise ValueError(f"{item['id']}: 可回答题必须有证据指针")
        for pointer in item["evidence"]:
            if not {"root_id", "file_name", "sha256", "pdf_page", "quote"}.issubset(pointer):
                raise ValueError(f"{item['id']}: evidence 指针字段不完整")
            if len(pointer["quote"]) > 180:
                raise ValueError(f"{item['id']}: 引文过长，S0 只保留短摘录")
            if pointer["pdf_page"] < 1 or len(pointer["sha256"]) != 64:
                raise ValueError(f"{item['id']}: 页码或 SHA-256 格式错误")
        items.append(item)
    if len(items) < 30:
        raise ValueError(f"黄金集至少需要 30 题，当前为 {len(items)}")
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("黄金集 id 重复")
    return items


def verify_quotes(items: list[dict[str, Any]], sources_path: Path) -> int:
    import fitz

    config = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    roots = {root["id"]: Path(root["path"]) for root in config.get("roots", [])}
    cache: dict[str, fitz.Document] = {}
    verified = 0
    try:
        for item in items:
            for pointer in item["evidence"]:
                if pointer["root_id"] not in roots:
                    raise ValueError(f"{item['id']}: 未知来源目录 {pointer['root_id']}")
                root = roots[pointer["root_id"]]
                candidates = [p for p in root.rglob(pointer["file_name"]) if p.is_file()]
                source = next((p for p in candidates if _sha256(p) == pointer["sha256"]), None)
                if source is None:
                    raise ValueError(f"{item['id']}: 找不到哈希匹配的只读源 PDF {pointer['file_name']}")
                if pointer["sha256"] not in cache:
                    cache[pointer["sha256"]] = fitz.open(source)
                doc = cache[pointer["sha256"]]
                page_number = pointer["pdf_page"]
                if page_number > doc.page_count:
                    raise ValueError(f"{item['id']}: PDF 页码超界 {page_number}")
                text = _normalize_excerpt(doc[page_number - 1].get_text("text"))
                if _normalize_excerpt(pointer["quote"]) not in text:
                    raise ValueError(f"{item['id']}: 短引文不在 {pointer['file_name']} PDF 第 {page_number} 页")
                verified += 1
    finally:
        for doc in cache.values():
            doc.close()
    return verified


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    args = parser.parse_args()
    items = load_gold(args.gold)
    verified = verify_quotes(items, args.sources)
    types = sorted({item["question_type"] for item in items})
    print(f"questions={len(items)} types={','.join(types)} evidence_quotes_verified={verified}")


if __name__ == "__main__":
    main()
