"""Run a disposable synthetic Web/MCP citation and ACL demonstration."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import fitz
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from papertrail.access import (Principal, assign_version_to_collection, create_collection,
                               read_evidence, search_papers)
from papertrail.mcp_server import handle
from papertrail.qa import ask
from papertrail.s1_index import index_selection, open_database
from papertrail.web import create_app


def _write_pdf(path: Path, title: str, sentence: str) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 55), title, fontsize=16)
    page.insert_textbox(fitz.Rect(40, 85, 550, 740), (sentence + " ") * 8, fontsize=11)
    doc.save(path)
    doc.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_selection(path: Path, digest: str) -> None:
    row = {"root_id": "demo", "file_name": "demo.pdf", "relative_path": "demo.pdf",
           "sha256": digest, "kind": "pdf", "source_type": "original_pdf"}
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def run_demo() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="papertrail-pt4-demo-") as raw_temp:
        root = Path(raw_temp)
        corpus = root / "corpus"
        corpus.mkdir()
        source = corpus / "demo.pdf"
        database = root / "papertrail.sqlite3"
        config = root / "sources.yaml"
        selection = root / "selection.jsonl"
        config.write_text(yaml.safe_dump({"roots": [{"id": "demo", "path": str(corpus)}]}),
                          encoding="utf-8")

        old_sha = _write_pdf(source, "Synthetic PT4 demo",
                             "DemoMarker provides a synthetic citation for ACL verification.")
        _write_selection(selection, old_sha)
        index_selection(database, config, selection)

        owner = Principal("demo-owner")
        create_collection(database, "demo-private", owner.user_id)
        conn = open_database(database)
        try:
            version_id = conn.execute(
                "SELECT version_id FROM paper_versions WHERE sha256=?", (old_sha,)
            ).fetchone()["version_id"]
        finally:
            conn.close()
        assign_version_to_collection(database, version_id, "demo-private")

        result = ask(database, "What does DemoMarker provide?", generate=False,
                     principal_id=owner.user_id)
        if result["status"] != "verified_excerpts" or not result["claims"]:
            raise RuntimeError("synthetic citation was not produced")
        citation = result["claims"][0]["evidence"]
        if citation["sha256"] != old_sha or citation["pdf_page"] != 1:
            raise RuntimeError("citation source or physical page did not match")

        app = create_app(database, principal_provider=lambda: owner)
        client = app.test_client()
        page = client.get(f"/?conversation_id={result['conversation_id']}")
        search_export = client.get("/api/search.jsonl?q=DemoMarker&query_id=pt4-demo")
        answer_export = client.get(f"/api/answer-eval/{result['conversation_id']}.jsonl")
        evidence_api = client.get(f"/api/evidence/{old_sha}/1")
        foreign_client = create_app(
            database, principal_provider=lambda: Principal("other-user")).test_client()
        foreign_search = foreign_client.get("/api/search?q=DemoMarker")
        mcp_read = handle(database, {
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": {"uri": f"papertrail://evidence/{old_sha}/1"},
        }, owner)
        if (page.status_code != 200 or search_export.status_code != 200
                or answer_export.status_code != 200 or evidence_api.status_code != 200
                or "result" not in mcp_read):
            raise RuntimeError("Web, JSONL, evidence API, or MCP citation read failed")
        page_html = page.get_data(as_text=True)
        search_rows = [json.loads(line) for line in search_export.get_data(as_text=True).splitlines()]
        if (citation["quote"] not in page_html or "PDF 第 1 页" not in page_html
                or not search_rows or search_rows[0]["source_sha256"] != old_sha
                or "text" in search_rows[0] or "snippet" in search_rows[0]
                or foreign_search.json["results"]):
            raise RuntimeError("Web locator, content-free search export, or HTTP ACL check failed")
        exported_rows = [json.loads(line) for line in answer_export.get_data(as_text=True).splitlines()]
        exported_evidence = exported_rows[0]["claims"][0]["evidence"][0]
        if (exported_evidence["source_sha256"] != old_sha
                or exported_evidence["pdf_page"] != citation["pdf_page"]
                or exported_evidence["snippet"] != citation["quote"]):
            raise RuntimeError("answer-evaluation export changed citation location")
        mcp_foreign_search = handle(database, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "search_papers", "arguments": {"query": "DemoMarker"}},
        }, Principal("other-user"))
        if mcp_foreign_search.get("result", {}).get("structuredContent", {}).get("results"):
            raise RuntimeError("foreign principal saw a source through MCP search")

        new_sha = _write_pdf(source, "Synthetic PT4 demo revised",
                             "RevisedMarker provides a replacement synthetic citation.")
        stale_search_hidden = not search_papers(database, "DemoMarker", owner, limit=5)
        stale_read_rejected = False
        try:
            read_evidence(database, old_sha, 1, owner)
        except ValueError:
            stale_read_rejected = True
        if not stale_search_hidden or not stale_read_rejected:
            raise RuntimeError("changed source remained searchable or directly readable")

        _write_selection(selection, new_sha)
        index_selection(database, config, selection, reconcile=True)
        revised = ask(database, "What does RevisedMarker provide?", generate=False,
                      principal_id=owner.user_id)
        if (revised["status"] != "verified_excerpts"
                or revised["claims"][0]["evidence"]["sha256"] != new_sha):
            raise RuntimeError("reconciled version did not retain owner access")
        old_version_removed = not search_papers(database, "DemoMarker", owner, limit=5)

        return {
            "synthetic_only": True,
            "models_called": 0,
            "private_files_read": 0,
            "web_citation_page": citation["pdf_page"],
            "citation_quote_and_page_visible_in_web": True,
            "search_export_omits_source_text": True,
            "answer_eval_export_matches_sha_and_page": True,
            "mcp_direct_read_allowed_for_owner": True,
            "cross_owner_search_denied_in_http_and_mcp": True,
            "changed_source_hidden_before_reconcile": stale_search_hidden,
            "changed_source_direct_read_rejected": stale_read_rejected,
            "owner_acl_preserved_after_reconcile": True,
            "old_version_removed_after_reconcile": old_version_removed,
        }


def main() -> None:
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
