import hashlib
import json
import sqlite3

import fitz
import yaml

from papertrail.access import (Principal, assign_version_to_collection, create_collection,
                               authorized_version_ids, read_evidence, search_papers)
from papertrail.mcp_server import _call, handle
from papertrail.s1_index import index_selection, open_database
from papertrail.web import create_app


def _indexed_library(tmp_path):
    root = tmp_path / "papers"
    root.mkdir()
    files = {
        "alpha.pdf": "alpha-only-needle Alice collection evidence",
        "beta.pdf": "beta-only-needle Bob collection evidence",
    }
    rows = []
    for filename, text in files.items():
        path = root / filename
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((40, 60), filename)
        page.insert_text((40, 100), text)
        doc.save(path)
        doc.close()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append({"root_id": "papers", "file_name": filename, "relative_path": filename,
                     "sha256": digest, "kind": "pdf", "source_type": "original_pdf"})
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "papers", "path": str(root)}]}), encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    database = tmp_path / "library.sqlite3"
    index_selection(database, config, selection)
    create_collection(database, "collection-b", "user-b")
    assign_version_to_collection(database, "v_" + rows[1]["sha256"], "collection-b")
    return database, rows


def test_collection_acl_filters_search_and_direct_evidence_reads(tmp_path):
    database, rows = _indexed_library(tmp_path)
    principal_a = Principal("local-dev")
    principal_b = Principal("user-b")

    assert {row["sha256"] for row in search_papers(database, "collection evidence", principal_a)} == {
        rows[0]["sha256"]}
    assert {row["sha256"] for row in search_papers(database, "collection evidence", principal_b)} == {
        rows[1]["sha256"]}
    assert "alpha-only-needle" in read_evidence(database, rows[0]["sha256"], 1, principal_a)["text"]

    for principal, foreign_row in ((principal_a, rows[1]), (principal_b, rows[0])):
        try:
            read_evidence(database, foreign_row["sha256"], 1, principal)
        except ValueError as exc:
            assert str(exc) == "original paper not found"
        else:
            raise AssertionError("cross-owner evidence read was allowed")


def test_http_and_mcp_share_acl_and_http_ignores_body_user_id(tmp_path):
    database, rows = _indexed_library(tmp_path)
    app = create_app(database)
    client = app.test_client()
    response = client.get("/api/search?q=collection%20evidence",
                          environ_overrides={"papertrail.principal": Principal("user-b")},
                          json={"user_id": "local-dev"})
    assert {row["sha256"] for row in response.json["results"]} == {rows[1]["sha256"]}

    direct = client.get(f"/api/evidence/{rows[0]['sha256']}/1",
                        environ_overrides={"papertrail.principal": Principal("user-b")})
    assert direct.status_code == 404

    mcp_search = _call(database, "search_papers", {"query": "collection evidence"}, Principal("user-b"))
    assert {row["sha256"] for row in mcp_search["structuredContent"]["results"]} == {rows[1]["sha256"]}
    mcp_read = handle(database, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "get_evidence", "arguments": {
                                     "sha256": rows[0]["sha256"], "page": 1}}}, Principal("user-b"))
    assert mcp_read["result"]["isError"] is True
    mcp_resource = handle(database, {"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                                     "params": {"uri": f"papertrail://documents/{rows[0]['sha256']}"}},
                          Principal("user-b"))
    assert mcp_resource["error"]["code"] == -32602


def test_default_single_user_principal_keeps_existing_local_library_access(tmp_path):
    database, rows = _indexed_library(tmp_path)
    app = create_app(database)
    client = app.test_client()

    response = client.get("/api/search?q=alpha-only-needle")
    assert response.status_code == 200
    assert [row["sha256"] for row in response.json["results"]] == [rows[0]["sha256"]]
    evidence = client.get(f"/api/evidence/{rows[0]['sha256']}/1")
    assert evidence.status_code == 200
    assert "alpha-only-needle" in evidence.json["text"]


def test_legacy_database_migrates_existing_versions_to_local_dev(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(database)
    conn.executescript("""
        CREATE TABLE papers(paper_id TEXT PRIMARY KEY,title_candidate TEXT NOT NULL,
            identity_basis TEXT NOT NULL,identity_value TEXT NOT NULL,
            identity_status TEXT NOT NULL DEFAULT 'provisional');
        CREATE TABLE paper_versions(version_id TEXT PRIMARY KEY,paper_id TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,source_type TEXT NOT NULL,file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL,page_count INTEGER,parseable_pages INTEGER,
            low_text_pages_json TEXT NOT NULL,parse_status TEXT NOT NULL,
            doi_candidates_json TEXT NOT NULL,parser_version TEXT NOT NULL,indexed_at TEXT NOT NULL);
        INSERT INTO papers VALUES('paper-1','Legacy paper','title','legacy','provisional');
        INSERT INTO paper_versions VALUES('version-1','paper-1','a','original_pdf','legacy.pdf',1,
            1,1,'[]','parsed','[]','old-parser','2026-01-01');
    """)
    conn.close()

    migrated = open_database(database)
    assert "collection_id" in {row[1] for row in migrated.execute("PRAGMA table_info(paper_versions)")}
    migrated.close()
    assert authorized_version_ids(database, "local-dev") == {"version-1"}
    assert authorized_version_ids(database, "user-b") == set()


def test_reindex_keeps_existing_collection_owner(tmp_path, monkeypatch):
    import papertrail.s1_index as s1_index

    database, rows = _indexed_library(tmp_path)
    monkeypatch.setattr(s1_index, "PARSER_VERSION", "acl-migration-test")
    index_selection(database, tmp_path / "sources.yaml", tmp_path / "selection.jsonl")

    assert [row["sha256"] for row in search_papers(
        database, "beta-only-needle", Principal("user-b"))] == [rows[1]["sha256"]]
    assert rows[1]["sha256"] not in {row["sha256"] for row in search_papers(
        database, "beta-only-needle", Principal("local-dev"))}
