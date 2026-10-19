"""Read-only S0 inventory for local PDF/Markdown/BibTeX sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz
import yaml

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
WORD_RE = re.compile(r"[\w]+", re.UNICODE)
TABLE_LINE_RE = re.compile(r"(?:\|.+\||\S.{1,35}\s{2,}\S.{1,35}\s{2,}\S)")
NON_PAPER_NAMES = {"client challenge", "access denied", "captcha"}
COVER_NOISE_RE = re.compile(r"^(?:proceedings\b|published as a conference paper\b|journal of\b|©|copyright\b|vol\.\s*\d|\d{1,4}$|arxiv:\s*\d)", re.I)


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(WORD_RE.findall(value))


def excluded(path: Path, segments: list[str]) -> bool:
    banned = {part.casefold() for part in segments}
    return any(part.casefold() in banned for part in path.parts)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate_title(path: Path, metadata_title: str, first_page: str) -> str:
    title = metadata_title.strip()
    if title and title.casefold() not in NON_PAPER_NAMES and not COVER_NOISE_RE.search(title):
        return title
    # PDF metadata is often blank. Use the first plausible short, non-contact line.
    for line in first_page.splitlines()[:30]:
        candidate = " ".join(line.split()).strip(" .:-")
        if COVER_NOISE_RE.search(candidate):
            continue
        if 12 <= len(candidate) <= 220 and not re.search(r"@|https?://|\b(arxiv|doi)\b", candidate, re.I):
            if len(candidate.split()) >= 3:
                return candidate
    return path.stem


def inspect_file(path: Path, root_id: str, kind: str) -> dict[str, Any]:
    stat = path.stat()
    row: dict[str, Any] = {
        "path": str(path.resolve()), "root_id": root_id, "kind": kind,
        "document_class": "paper_candidate" if kind == "pdf" else ("reading_note" if kind == "md" else "bibliography"),
        "sha256": _hash(path), "size_bytes": stat.st_size,
        "title_candidate": path.stem, "doi_candidates": [],
        "page_count": None, "parseable_pages": None, "parseable_page_ratio": None,
        "scan_pages": [], "table_dense_pages": [], "parse_status": "not_applicable",
        "quality_notes": [],
    }
    if kind == "pdf":
        try:
            with fitz.open(path) as doc:
                metadata = doc.metadata or {}
                page_texts = [page.get_text("text") for page in doc]
                all_sample = "\n".join(page_texts[:2])
                row["title_candidate"] = _candidate_title(path, metadata.get("title") or "", page_texts[0] if page_texts else "")
                parseable = [i for i, text in enumerate(page_texts, 1) if len(WORD_RE.findall(text)) >= 12]
                row["page_count"] = doc.page_count
                row["parseable_pages"] = len(parseable)
                row["parseable_page_ratio"] = round(len(parseable) / doc.page_count, 4) if doc.page_count else 0.0
                row["scan_pages"] = [i for i, text in enumerate(page_texts, 1) if len(WORD_RE.findall(text)) < 12]
                row["table_dense_pages"] = [i for i, text in enumerate(page_texts, 1)
                                            if sum(bool(TABLE_LINE_RE.search(line)) for line in text.splitlines()) >= 8]
                row["doi_candidates"] = sorted({match.rstrip(".,;)").casefold() for match in DOI_RE.findall(all_sample)})
                row["parse_status"] = "ok" if doc.page_count else "empty_pdf"
                joined_lower = all_sample.casefold()
                if any(marker in joined_lower for marker in ("client challenge", "enable javascript to proceed", "captcha", "checking your browser")):
                    row["document_class"] = "non_paper_suspect"
                    row["quality_notes"].append("疑似网页拦截/非论文 PDF，需人工判定")
                if any(marker in path.stem for marker in ("精读", "合并材料", "毕设关联")):
                    row["document_class"] = "reading_note_pdf"
                if row["parseable_page_ratio"] == 0:
                    row["quality_notes"].append("无可提取文本；扫描件或受保护 PDF 待人工确认")
                elif row["parseable_page_ratio"] < 0.8:
                    row["quality_notes"].append("可解析页比例低于 0.80")
                if row["title_candidate"] == path.stem:
                    row["quality_notes"].append("题名来自文件名，待人工校对")
        except Exception as exc:  # inventory must preserve unreadable candidates
            row["parse_status"] = "error"
            row["quality_notes"].append(f"PDF 读取失败：{type(exc).__name__}")
    elif kind == "md":
        try:
            sample = path.read_text(encoding="utf-8", errors="replace")
            row["title_candidate"] = next((line.lstrip("# ").strip() for line in sample.splitlines() if line.strip()), path.stem)
            row["doi_candidates"] = sorted({match.rstrip(".,;)").casefold() for match in DOI_RE.findall(sample[:250_000])})
            row["parse_status"] = "ok"
        except OSError as exc:
            row["parse_status"] = "error"
            row["quality_notes"].append(f"Markdown 读取失败：{type(exc).__name__}")
    elif kind == "bib":
        try:
            sample = path.read_text(encoding="utf-8", errors="replace")
            row["doi_candidates"] = sorted({match.rstrip(".,;)").casefold() for match in DOI_RE.findall(sample)})
            row["parse_status"] = "ok"
        except OSError as exc:
            row["parse_status"] = "error"
            row["quality_notes"].append(f"BibTeX 读取失败：{type(exc).__name__}")
    return row


def discover(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    banned = config.get("exclude_path_segments", [])
    for root in config.get("roots", []):
        base = Path(root["path"])
        if not base.is_dir():
            issues.append(f"缺失源目录：{root['id']} — {base}")
            continue
        allowed = {f".{ext.lower().lstrip('.')}" for ext in root.get("kinds", [])}
        candidates = sorted(p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in allowed and not excluded(p, banned))
        for path in candidates:
            kind = path.suffix.lower().lstrip(".")
            rows.append(inspect_file(path, root["id"], kind))
    for item in config.get("bibliography", []):
        path = Path(item["path"])
        if path.is_file() and not excluded(path, banned):
            rows.append(inspect_file(path, item["id"], "bib"))
        else:
            issues.append(f"缺失 BibTeX：{item['id']} — {path}")
    rows.sort(key=lambda row: (row["root_id"], row["path"].casefold()))
    return rows, issues


def duplicate_groups(rows: list[dict[str, Any]]) -> tuple[list[list[dict[str, Any]]], list[list[dict[str, Any]]]]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["kind"] != "pdf":
            continue
        by_hash[row["sha256"]].append(row)
    exact = [group for group in by_hash.values() if len(group) > 1]
    papers = [row for row in rows if row["kind"] == "pdf" and row["document_class"] == "paper_candidate"]
    parent = list(range(len(papers)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for i, left in enumerate(papers):
        left_doi = set(left["doi_candidates"])
        left_title = normalize_title(left["title_candidate"])
        for j in range(i + 1, len(papers)):
            right = papers[j]
            right_title = normalize_title(right["title_candidate"])
            similarity = SequenceMatcher(None, left_title, right_title).ratio()
            doi_match = bool(left_doi.intersection(right["doi_candidates"])) and similarity >= 0.60
            title_match = min(len(left_title), len(right_title)) >= 24 and similarity >= 0.84
            if doi_match or title_match:
                union(i, j)
    components: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(papers):
        components[find(index)].append(row)
    related = [group for group in components.values() if len({r["sha256"] for r in group}) > 1]
    exact.sort(key=lambda g: g[0]["sha256"])
    related.sort(key=lambda g: (g[0]["doi_candidates"][:1], normalize_title(g[0]["title_candidate"])))
    return exact, related


def render_report(rows: list[dict[str, Any]], issues: list[str]) -> str:
    exact, related = duplicate_groups(rows)
    pdfs = [r for r in rows if r["kind"] == "pdf"]
    by_root: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        by_root[row["root_id"]][row["kind"]] += 1
    parsed_pages = sum(r["parseable_pages"] or 0 for r in pdfs)
    total_pages = sum(r["page_count"] or 0 for r in pdfs)
    scan_rows = [r for r in pdfs if r["scan_pages"]]
    poor_rows = [r for r in pdfs if r["parse_status"] != "ok" or (r["parseable_page_ratio"] or 0) < 0.8]
    lines = [
        "# S0 文献盘点与数据质量", "",
        "扫描为只读；此报告保存统计、异常与指纹，不保存 PDF 全文。SHA-256 用于字节级重复判断。DOI/题名匹配只产生人工核对候选，不自动合并版本。",
        "", "## 路径计数", "", "| 来源 ID | PDF | Markdown | BibTeX |", "|---|---:|---:|---:|",
    ]
    for root_id in sorted(by_root):
        c = by_root[root_id]
        lines.append(f"| `{root_id}` | {c['pdf']} | {c['md']} | {c['bib']} |")
    unique_pdf_hashes = len({r["sha256"] for r in pdfs})
    lines += ["", "## 汇总", "", f"- 文件记录：{len(rows)}（PDF {len(pdfs)}；独立 PDF 内容哈希 {unique_pdf_hashes}；Markdown {sum(r['kind']=='md' for r in rows)}；BibTeX {sum(r['kind']=='bib' for r in rows)}）。",
              f"- PDF 页数：{total_pages}；可解析页：{parsed_pages}（加权比例 {parsed_pages / total_pages:.1%}）。",
              f"- PDF 中含扫描/低文本页的文件：{len(scan_rows)}；低于 80% 可解析比例或读取失败的文件：{len(poor_rows)}。",
              f"- 字节级重复组：{len(exact)}；同 DOI/规范化题名、但内容哈希不同的待核对组：{len(related)}。",
              "- 页面级表格密集候选：按多列对齐/竖线行启发式标记，仅供抽样复核；无法可靠判断论文语义上的表格。",
              "", "## 完全重复（SHA-256）", ""]
    if exact:
        for i, group in enumerate(exact, 1):
            lines.append(f"### 重复组 {i} — `{group[0]['sha256'][:16]}`")
            for row in group:
                lines.append(f"- `{row['root_id']}` · `{Path(row['path']).name}` · {row['kind']}")
    else:
        lines.append("无")
    lines += ["", "## 同论文/版本候选（非完全重复）", ""]
    if related:
        for i, group in enumerate(related, 1):
            doi = next(iter(group[0]["doi_candidates"]), "无 DOI 候选")
            lines.append(f"### 候选组 {i} — {doi} — {group[0]['title_candidate'][:120]}")
            for row in group:
                lines.append(f"- `{row['root_id']}` · `{Path(row['path']).name}` · SHA `{row['sha256'][:12]}`")
    else:
        lines.append("无自动候选；文件名/元数据题名不充分时仍需人工比对。")
    lines += ["", "## 解析异常与质量复核", ""]
    if poor_rows:
        lines += ["| 来源 | 文件 | 页数 | 可解析比例 | 扫描/低文本页 | 表格密集候选页 | 状态 |", "|---|---|---:|---:|---|---|---|"]
        for row in poor_rows:
            ratio = "—" if row["parseable_page_ratio"] is None else f"{row['parseable_page_ratio']:.1%}"
            lines.append(f"| `{row['root_id']}` | `{Path(row['path']).name}` | {row['page_count'] if row['page_count'] is not None else '—'} | {ratio} | {row['scan_pages'] or '—'} | {row['table_dense_pages'] or '—'} | {row['parse_status']} |")
    else:
        lines.append("无")
    quality_rows = [r for r in rows if r["quality_notes"]]
    lines += ["", "## 人工复核标记", ""]
    if quality_rows:
        for row in quality_rows:
            lines.append(f"- `{row['root_id']}` · `{Path(row['path']).name}`: {'；'.join(row['quality_notes'])}")
    else:
        lines.append("无")
    dense_rows = [r for r in pdfs if r["table_dense_pages"]]
    lines += ["", "## 表格密集页候选", ""]
    if dense_rows:
        for row in dense_rows:
            lines.append(f"- `{row['root_id']}` · `{Path(row['path']).name}`：PDF 页 {', '.join(map(str, row['table_dense_pages']))}")
    else:
        lines.append("当前启发式未标出候选页；这不代表文献没有表格。")
    lines += ["", "## 缺失源", ""]
    lines.extend(f"- {issue}" for issue in issues) if issues else lines.append("无")
    lines += ["", "## 清理/排除规则", "", "递归扫描配置中的扩展名；路径任一段命中 `reproduction`、`reports`、`figures`、`.tmp`、`output`、`__pycache__` 即排除。源表只包含计划列出的资料目录；其他位置不扫描。对输出目录和报告本身不做递归发现。", "", "## 文件级清单", "", "下表列出每个发现项的绝对路径、SHA-256、文件类型/候选类别、字节数、PDF 页数与可解析页比例、候选 DOI 和题名。PDF 页码按物理 PDF 页计。DOI 只从 PDF 前两页提取，仍可能是引文而非本文 DOI；DOI/题名匹配只产生人工核对候选，不自动合并版本。", "", "| 来源 ID | 绝对路径 | SHA-256 | 类型 | 文档类别 | 字节 | 页数 | 可解析页比例 | 候选 DOI | 候选题名 |", "|---|---|---|---|---|---:|---:|---:|---|---|---|"]
    for row in rows:
        ratio = "—" if row["parseable_page_ratio"] is None else f"{row['parseable_page_ratio']:.1%}"
        doi = ", ".join(row["doi_candidates"]) or "—"
        title = row["title_candidate"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{row['root_id']}` | `{row['path']}` | `{row['sha256']}` | {row['kind']} | {row['document_class']} | {row['size_bytes']} | {row['page_count'] if row['page_count'] is not None else '—'} | {ratio} | {doi} | {title} |")
    lines.append("")
    return "\n".join(lines)


def run(sources: Path, report: Path, inventory: Path) -> None:
    config = yaml.safe_load(sources.read_text(encoding="utf-8"))
    rows, issues = discover(config)
    report.parent.mkdir(parents=True, exist_ok=True)
    inventory.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(rows, issues), encoding="utf-8")
    inventory.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"files={len(rows)} pdf={sum(r['kind']=='pdf' for r in rows)} exact_duplicate_groups={len(duplicate_groups(rows)[0])}")
    print(f"report={report} inventory={inventory}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inventory-out", type=Path, required=True)
    args = parser.parse_args()
    run(args.sources, args.out, args.inventory_out)


if __name__ == "__main__":
    main()
