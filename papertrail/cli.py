"""Command line interface for the S1 retrieval baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .s1_index import database_summary, index_selection, inspect_document, search
from .retrieval import build_vector_index, retrieve


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="papertrail", description="PaperTrail S1：只读文献解析与本机关键词检索")
    commands = parser.add_subparsers(dest="command", required=True)

    index_parser = commands.add_parser("index", help="将配置中明确选择的 PDF/Markdown 建入本地 FTS5 索引")
    index_parser.add_argument("--sources", type=Path, required=True)
    index_parser.add_argument("--selection", type=Path, required=True)
    index_parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    index_parser.add_argument("--ocr-fallback", action="store_true", help="对低文本 PDF 页尝试本机 Tesseract OCR；OCR 派生文本会单独标记")

    search_parser = commands.add_parser("search", help="检索并显示来源、PDF 页码与 BM25 排序分")
    search_parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--source-type", choices=["original_pdf", "reading_note"])
    search_parser.add_argument("--mode", choices=["bm25", "vector", "hybrid"], default="bm25")
    search_parser.add_argument("--vector-artifact", type=Path)

    vector_parser = commands.add_parser("vector-build", help="建立本地潜在语义向量索引")
    vector_parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    vector_parser.add_argument("--artifact", type=Path)

    inspect_parser = commands.add_parser("inspect", help="查看文献版本、解析情况、页码和索引块数量")
    inspect_parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    inspect_parser.add_argument("--document", required=True, help="SHA-256、version_id 或 paper_id 前缀")

    status_parser = commands.add_parser("status", help="查看本机索引计数")
    status_parser.add_argument("--db", type=Path, default=Path(".local/papertrail.sqlite3"))
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    try:
        if args.command == "index":
            _print_json(index_selection(args.db, args.sources, args.selection, args.ocr_fallback))
        elif args.command == "search":
            results = retrieve(args.db, args.query, args.limit, args.source_type, args.mode, args.vector_artifact)
            if not results:
                print("没有匹配结果。请确认索引已建立，并检查英文术语/题名关键词。")
                return 0
            for rank, result in enumerate(results, 1):
                page = f"PDF 第 {result['pdf_page']} 页" if result["pdf_page"] is not None else "Markdown 笔记"
                print(f"[{rank}] score={result['rank_score']:.5f} | {result['source_type']} | {result['title']} | {page}")
                print(f"    章节：{result['section']}")
                print(f"    SHA-256：{result['sha256']}")
                if result.get("text_origin") == "ocr_derived":
                    print("    文本来源：OCR 派生文本（仅作检索线索，引用前必须人工核验原页）")
                print(f"    路径：{result['path']}")
                print(f"    文本：{result['text'][:500].replace(chr(10), ' ')}")
                if result.get("retrieval_signals"):
                    print(f"    信号：{', '.join(result['retrieval_signals'])}")
        elif args.command == "vector-build":
            artifact = args.artifact or args.db.with_name(args.db.stem + ".vectors.joblib")
            _print_json(build_vector_index(args.db, artifact))
        elif args.command == "inspect":
            result = inspect_document(args.db, args.document)
            if result is None:
                print("没有找到该文献版本。")
                return 1
            _print_json(result)
        elif args.command == "status":
            _print_json(database_summary(args.db))
        return 0
    except (ValueError, OSError) as exc:
        print(f"PaperTrail: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
