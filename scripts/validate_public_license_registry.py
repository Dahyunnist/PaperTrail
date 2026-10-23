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
            elif parsed.netloc not in {"nature.com", "www.nature.com", "pmc.ncbi.nlm.nih.gov", "journals.plos.org", "ai.jmir.org", "academic.oup.com"}:
                errors.append(f"{label} {field} 不属于登记的官方来源域")
        download_url = paper.get("download_url")
        if download_url:
            parsed = urlparse(str(download_url))
            if parsed.scheme != "https" or parsed.netloc not in {"journals.plos.org", "ai.jmir.org", "pmc.ncbi.nlm.nih.gov", "academic.oup.com", "www.nature.com"}:
                errors.append(f"{label} download_url 不属于 HTTPS 官方来源域")
        source_hash = paper.get("local_pdf_sha256")
        if source_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", source_hash):
            errors.append(f"{label} local_pdf_sha256 格式无效")
        license_detail = paper.get("license_detail")
        if license_detail and license_detail != "https://creativecommons.org/licenses/by/4.0/":
            errors.append(f"{label} license_detail 不是 CC BY 4.0 官方许可文本")
        if paper.get("benchmark_status", "").startswith("冻结") and source_hash is None:
            errors.append(f"{label} 冻结基准缺少本地 PDF SHA-256")
        local_file = paper.get("local_pdf")
        if local_file:
            project_root = path.resolve().parents[1]
            pdf_path = (project_root / local_file).resolve()
            if not pdf_path.is_relative_to(project_root) or not pdf_path.is_file():
                errors.append(f"{label} 本地来源文件缺失或越出项目目录")
            elif source_hash and hashlib.sha256(pdf_path.read_bytes()).hexdigest() != source_hash:
                errors.append(f"{label} 本地 PDF SHA-256 不匹配")
    return errors


if __name__ == "__main__":
    problems = validate(Path(sys.argv[1]) if len(sys.argv) > 1 else REGISTRY)
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("许可证登记结构、许可范围和来源域检查通过；未联网核验页面内容。")
