"""Offline structural checks for the public-paper license registry."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


REGISTRY = Path(__file__).resolve().parents[1] / "configs" / "public-paper-license-registry.json"


def validate(path: Path = REGISTRY) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("schema_version") != 1 or not isinstance(data.get("papers"), list):
        return ["registry schema_version 或 papers 字段无效"]
    seen: set[str] = set()
    for number, paper in enumerate(data["papers"], 1):
        label = f"第 {number} 条"
        for field in ("title", "public_record", "license", "license_evidence", "local_pdf_sha256", "benchmark_status"):
            if field not in paper:
                errors.append(f"{label} 缺字段 {field}")
        key = paper.get("doi") or paper.get("pmcid")
        if not key or key in seen:
            errors.append(f"{label} DOI/PMCID 缺失或重复")
        seen.add(key)
        if paper.get("license") != "CC BY 4.0":
            errors.append(f"{label} 许可不在允许范围")
        for field in ("public_record", "license_evidence"):
            parsed = urlparse(str(paper.get(field, "")))
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"{label} {field} 必须是 HTTPS 官方来源")
            elif parsed.netloc not in {"nature.com", "www.nature.com", "pmc.ncbi.nlm.nih.gov"}:
                errors.append(f"{label} {field} 不属于登记的官方来源域")
        source_hash = paper.get("local_pdf_sha256")
        if source_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", source_hash):
            errors.append(f"{label} local_pdf_sha256 格式无效")
        if paper.get("benchmark_status", "").startswith("冻结") and source_hash is None:
            errors.append(f"{label} 冻结基准缺少本地 PDF SHA-256")
        local_file = paper.get("local_pdf")
        if local_file:
            pdf_path = (path.parent / local_file).resolve()
            if not pdf_path.is_relative_to(path.parent.resolve()) or not pdf_path.is_file():
                errors.append(f"{label} 本地来源文件缺失或越出登记目录")
            elif source_hash and hashlib.sha256(pdf_path.read_bytes()).hexdigest() != source_hash:
                errors.append(f"{label} 本地 PDF SHA-256 不匹配")
    return errors


if __name__ == "__main__":
    problems = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else REGISTRY)
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("许可证登记结构、许可范围和来源域检查通过；未联网核验页面内容。")
