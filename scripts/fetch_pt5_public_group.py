"""Fetch the frozen PT5 CC BY corpus from official PLOS download endpoints."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "public-paper-license-registry.json"
GROUP = "pt5-public-real-20261023"
MANIFEST = ROOT / "evals" / "pt5-public-source-manifest-20261023.json"
ALLOWED_HOSTS = {"journals.plos.org"}


def _save_registry(data: dict) -> None:
    temp = REGISTRY.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, REGISTRY)


def _fetch(client: httpx.Client, paper: dict, target: Path) -> str:
    if paper.get("license") != "CC BY 4.0":
        raise ValueError(f"拒绝下载未确认 CC BY 4.0 的来源：{paper.get('title')}")
    url = paper.get("download_url", "")
    if urlparse(url).hostname not in ALLOWED_HOSTS:
        raise ValueError(f"下载域不在官方许可列表：{url}")
    expected_sha = paper.get("local_pdf_sha256")
    if not target.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"登记路径越出项目目录：{target}")
    if target.exists():
        actual_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected_sha and actual_sha == expected_sha:
            return actual_sha
        raise FileExistsError(f"拒绝覆盖未核验的现有文件：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    saw_header = False
    temp_path: Path | None = None
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            final_host = urlparse(str(response.url)).hostname
            if final_host not in ALLOWED_HOSTS:
                raise ValueError(f"下载重定向离开官方许可域：{final_host}")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
            if content_type != "application/pdf":
                raise ValueError(f"官方来源未返回 PDF：{content_type}")
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".pt5-", suffix=".part",
                                             delete=False) as stream:
                temp_path = Path(stream.name)
                for block in response.iter_bytes():
                    if not block:
                        continue
                    if not saw_header:
                        if not block.startswith(b"%PDF-"):
                            raise ValueError("来源文件没有 PDF 文件头")
                        saw_header = True
                    digest.update(block)
                    stream.write(block)
        if not saw_header:
            raise ValueError("来源 PDF 为空")
        actual_sha = digest.hexdigest()
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(f"来源哈希与冻结登记不符：{paper['title']}")
        os.replace(temp_path, target)
        temp_path = None
        return actual_sha
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    papers = [paper for paper in data["papers"] if paper.get("benchmark_group") == GROUP]
    if len(papers) != 3:
        raise SystemExit(f"{GROUP} 应有 3 篇论文，实际为 {len(papers)}")
    with httpx.Client(follow_redirects=True, timeout=90, headers={"User-Agent": "PaperTrail/0.1 CC-BY benchmark fetch"}) as client:
        for paper in papers:
            target = ROOT / paper["local_pdf"]
            sha = _fetch(client, paper, target)
            paper["local_pdf_sha256"] = sha
            paper["benchmark_status"] = "官方出版者 PDF 已下载并校验 SHA-256；等待人工页级黄金题冻结"
            _save_registry(data)
            print(f"{paper['doi']} {sha}")
    manifest = {
        "schema_version": 1,
        "group_id": GROUP,
        "status": "source_files_frozen_gold_pending",
        "license": "CC BY 4.0",
        "sources": [{key: paper.get(key) for key in (
            "title", "doi", "source_version", "public_record", "license_evidence",
            "download_url", "local_pdf", "local_pdf_sha256")} for paper in papers],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(MANIFEST.relative_to(ROOT))


if __name__ == "__main__":
    main()
