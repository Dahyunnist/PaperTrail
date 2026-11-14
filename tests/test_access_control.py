import hashlib
import json
import sqlite3

import fitz
import yaml

from papertrail.access import (Principal, assign_version_to_collection, create_collection,
                               authorized_version_ids, read_evidence, search_papers)
from papertrail.mcp_server import _call, _resource_list, handle
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


def test_mcp_direct_resources_enforce_collection_acl(tmp_path):
    database, rows = _indexed_library(tmp_path)
    foreign_sha = rows[0]["sha256"]
    own_sha = rows[1]["sha256"]
    principal = Principal("user-b")
    assert {item["uri"] for item in _resource_list(database, principal)} == {
        f"papertrail://documents/{own_sha}"}

    for uri in (f"papertrail://documents/{foreign_sha}",
                f"papertrail://evidence/{foreign_sha}/1"):
        response = handle(database, {"jsonrpc": "2.0", "id": 11,
                                     "method": "resources/read", "params": {"uri": uri}}, principal)
        assert response["error"]["code"] == -32602
    own = handle(database, {"jsonrpc": "2.0", "id": 12, "method": "resources/read",
                            "params": {"uri": f"papertrail://evidence/{own_sha}/1"}}, principal)
    assert "beta-only-needle" in own["result"]["contents"][0]["text"]


def test_replaced_version_hides_stale_search_and_preserves_acl_across_web_mcp_resources(tmp_path):
    database, rows = _indexed_library(tmp_path)
    root = tmp_path / "papers"
    beta = root / "beta.pdf"
    replacement = fitz.open()
    page = replacement.new_page()
    page.insert_text((40, 60), "beta.pdf revised")
    page.insert_text((40, 100), "beta revised-only synthetic collection evidence")
    replacement.save(beta)
    replacement.close()
    old_sha = rows[1]["sha256"]
    new_sha = hashlib.sha256(beta.read_bytes()).hexdigest()

    client = create_app(database).test_client()
    user_b = {"papertrail.principal": Principal("user-b")}
    stale_web = client.get("/api/search?q=beta-only-needle", environ_overrides=user_b)
    assert stale_web.status_code == 200 and stale_web.json["results"] == []
    stale_mcp = _call(database, "search_papers", {"query": "beta-only-needle"}, Principal("user-b"))
    assert stale_mcp["structuredContent"]["results"] == []
    listed_before_reconcile = handle(database, {"jsonrpc": "2.0", "id": 40,
                                                "method": "resources/list"}, Principal("user-b"))
    assert all(old_sha not in item["uri"] for item in listed_before_reconcile["result"]["resources"])

    selection = tmp_path / "selection.jsonl"
    updated_rows = [dict(rows[0]), dict(rows[1], sha256=new_sha)]
    selection.write_text("".join(json.dumps(row) + "\n" for row in updated_rows), encoding="utf-8")
    assert index_selection(database, tmp_path / "sources.yaml", selection, reconcile=True)["added"] == 1

    web_b = client.get("/api/search?q=beta%20revised-only", environ_overrides=user_b)
    assert {row["sha256"] for row in web_b.json["results"]} == {new_sha}
    web_a = client.get("/api/search?q=beta%20revised-only")
    assert new_sha not in {row["sha256"] for row in web_a.json["results"]}
    mcp_b = _call(database, "search_papers", {"query": "beta revised-only"}, Principal("user-b"))
    assert {row["sha256"] for row in mcp_b["structuredContent"]["results"]} == {new_sha}
    mcp_a = _call(database, "search_papers", {"query": "beta revised-only"}, Principal("local-dev"))
    assert new_sha not in {row["sha256"] for row in mcp_a["structuredContent"]["results"]}
    assert client.get(f"/api/evidence/{new_sha}/1", environ_overrides=user_b).status_code == 200
    assert client.get(f"/api/evidence/{new_sha}/1").status_code == 404
    listed_after_reconcile = handle(database, {"jsonrpc": "2.0", "id": 41,
                                               "method": "resources/list"}, Principal("user-b"))
    assert {item["uri"] for item in listed_after_reconcile["result"]["resources"]} == {
        f"papertrail://documents/{new_sha}"}
    assert handle(database, {"jsonrpc": "2.0", "id": 42, "method": "resources/read",
                             "params": {"uri": f"papertrail://evidence/{new_sha}/1"}},
                  Principal("user-b"))["result"]["contents"]
    assert handle(database, {"jsonrpc": "2.0", "id": 43, "method": "resources/read",
                             "params": {"uri": f"papertrail://evidence/{new_sha}/1"}},
                  Principal("local-dev"))["error"]["code"] == -32602


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


def test_jsonl_search_export_applies_acl_and_omits_content(tmp_path):
    database, rows = _indexed_library(tmp_path)
    client = create_app(database).test_client()
    principal_a = {"papertrail.principal": Principal("local-dev")}
    principal_b = {"papertrail.principal": Principal("user-b")}
    response_a = client.get("/api/search.jsonl?q=collection%20evidence", environ_overrides=principal_a)
    response_b = client.get("/api/search.jsonl?q=collection%20evidence", environ_overrides=principal_b)
    records_a = [json.loads(line) for line in response_a.data.decode().splitlines()]
    records_b = [json.loads(line) for line in response_b.data.decode().splitlines()]
    assert {row["source_sha256"] for row in records_a} == {rows[0]["sha256"]}
    assert {row["source_sha256"] for row in records_b} == {rows[1]["sha256"]}
    assert response_a.headers["X-Export-Scope"] == "retrieval-only"
    assert all(set(row) == {"record_type", "query_id", "source_sha256", "pdf_page", "chunk_id", "rank_score"}
               for row in records_a + records_b)
    assert all(row["record_type"] == "retrieval_result" for row in records_a + records_b)
    assert "alpha-only-needle" not in response_a.get_data(as_text=True)


def test_jsonl_search_export_omits_stale_source_after_hash_changes(tmp_path):
    database, rows = _indexed_library(tmp_path)
    pdf = tmp_path / "papers" / "alpha.pdf"
    replacement = fitz.open()
    page = replacement.new_page()
    page.insert_text((40, 60), "alpha revised with changed source bytes")
    replacement.save(pdf)
    replacement.close()
    response = create_app(database).test_client().get(
        "/api/search.jsonl?q=alpha%20collection%20evidence",
        environ_overrides={"papertrail.principal": Principal("local-dev")})
    records = [json.loads(line) for line in response.data.decode().splitlines()]
    assert rows[0]["sha256"] not in {row["source_sha256"] for row in records}


def test_answer_eval_export_denies_foreign_principal_even_for_empty_claims(tmp_path, monkeypatch):
    import papertrail.qa as qa
    database, _rows = _indexed_library(tmp_path)
    monkeypatch.delenv("PAPERTRAIL_LLM_MODEL", raising=False)
    result = qa.ask(database, "notpresenttoken", mode="bm25", generate=False)
    assert result["claims"] == []
    response = create_app(database).test_client().get(
        f"/api/answer-eval/{result['conversation_id']}.jsonl",
        environ_overrides={"papertrail.principal": Principal("user-b")})
    assert response.status_code == 404


def _qa_claim_fixture(tmp_path, quote=None):
    database, rows = _indexed_library(tmp_path)
    digest = rows[0]["sha256"]
    pdf = tmp_path / "papers" / "alpha.pdf"
    with fitz.open(pdf) as doc:
        page_text = doc[0].get_text("text")
    quote = quote or page_text.strip()
    import papertrail.qa as qa
    conn = open_database(database)
    try:
        qa._ensure_qa_schema(conn)
        conn.execute("INSERT INTO qa_conversations(conversation_id,title,created_at,updated_at,owner_id) VALUES(?,?,?,?,?)",
                     ("answer-eval-fixture", "fixture", "2026-11-13T00:00:00+00:00",
                      "2026-11-13T00:00:00+00:00", "local-dev"))
        conn.execute("INSERT INTO qa_turns(turn_id,conversation_id,question,answer,status,retrieval_mode,context_query,created_at,coverage_json,coverage_complete) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     ("turn-fixture", "answer-eval-fixture", "Fixture question", "Fixture answer",
                      "generated_claims_reviewed", "bm25", None, "2026-11-13T00:00:00+00:00", "[]", 1))
        evidence = {"sha256": digest, "pdf_page": 1, "quote": quote, "support_evidence": [
            {"sha256": digest, "pdf_page": 1, "quote": quote}]}
        conn.execute("INSERT INTO qa_claims VALUES(?,?,?,?,?)",
                     ("claim-fixture", "turn-fixture", 1, "Fixture claim", json.dumps(evidence)))
        conn.commit()
    finally:
        conn.close()
    return database, pdf


def test_answer_eval_jsonl_exports_claim_and_truncates_verified_evidence(tmp_path):
    database, _pdf = _qa_claim_fixture(tmp_path)
    client = create_app(database).test_client()
    response = client.get("/api/answer-eval/answer-eval-fixture.jsonl",
                          environ_overrides={"papertrail.principal": Principal("local-dev")})
    assert response.status_code == 200
    record = json.loads(response.data.decode().splitlines()[0])
    assert record["question"] == "Fixture question" and record["answer"] == "Fixture answer"
    assert record["claims"][0]["text"] == "Fixture claim"
    assert record["claims"][0]["evidence"][0]["snippet"]
    assert record["claims"][0]["evidence"][0]["snippet_truncated"] is False
    assert record["human_score"] is None and record["reviewer"] is None


def test_answer_eval_jsonl_rejects_expired_claim_source(tmp_path):
    database, pdf = _qa_claim_fixture(tmp_path)
    doc = fitz.open()
    doc.new_page().insert_text((40, 60), "replacement source has different bytes")
    doc.save(pdf)
    doc.close()
    response = create_app(database).test_client().get(
        "/api/answer-eval/answer-eval-fixture.jsonl",
        environ_overrides={"papertrail.principal": Principal("local-dev")})
    assert response.status_code == 404


def test_answer_eval_jsonl_truncates_long_evidence_snippet(tmp_path):
    database, rows = _indexed_library(tmp_path)
    pdf = tmp_path / "papers" / "alpha.pdf"
    long_text = ("verifiable synthetic evidence phrase " * 20).strip()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(30, 30, 560, 800), long_text, fontsize=9)
    doc.save(pdf)
    doc.close()
    # Reindex fixture to make the replacement SHA an authorized current version.
    config, selection = tmp_path / "sources.yaml", tmp_path / "selection.jsonl"
    rows[0]["sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
    selection.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    index_selection(database, config, selection, reconcile=True)
    conn = open_database(database)
    try:
        import papertrail.qa as qa
        qa._ensure_qa_schema(conn)
        ev = {"sha256": rows[0]["sha256"], "pdf_page": 1, "quote": long_text,
              "support_evidence": [{"sha256": rows[0]["sha256"], "pdf_page": 1, "quote": long_text}]}
        conn.execute("INSERT INTO qa_conversations(conversation_id,title,created_at,updated_at,owner_id) VALUES(?,?,?,?,?)",
                     ("long-evidence", "fixture", "now", "now", "local-dev"))
        conn.execute("INSERT INTO qa_turns(turn_id,conversation_id,question,answer,status,retrieval_mode,context_query,created_at,coverage_json,coverage_complete) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     ("long-turn", "long-evidence", "q", "a", "generated_partial", "bm25", None, "now", "[]", 0))
        conn.execute("INSERT INTO qa_claims VALUES(?,?,?,?,?)",
                     ("long-claim", "long-turn", 1, "claim", json.dumps(ev)))
        conn.commit()
    finally:
        conn.close()
    response = create_app(database).test_client().get(
        "/api/answer-eval/long-evidence.jsonl", environ_overrides={"papertrail.principal": Principal("local-dev")})
    assert response.status_code == 200
    evout = json.loads(response.data.decode())["claims"][0]["evidence"][0]
    assert len(evout["snippet"]) == 500 and evout["snippet_truncated"] is True


def test_qa_conversation_owner_is_bound_and_checked_on_reuse_and_history(tmp_path, monkeypatch):
    import papertrail.qa as qa
    database, _rows = _indexed_library(tmp_path)
    monkeypatch.delenv("PAPERTRAIL_LLM_MODEL", raising=False)
    result = qa.ask(database, "notpresenttoken", mode="bm25", generate=False,
                    conversation_id="owned-conversation", principal_id="user-b")
    assert result["claims"] == []
    assert qa.conversation_history(database, "owned-conversation", "user-b")
    import pytest
    with pytest.raises(ValueError, match="conversation not found"):
        qa.conversation_history(database, "owned-conversation", "local-dev")
    with pytest.raises(ValueError, match="conversation not found"):
        qa.ask(database, "follow up", conversation_id="owned-conversation",
               generate=False, principal_id="local-dev")


def test_updated_and_deleted_sources_invalidate_old_citations_across_http_and_mcp(tmp_path):
    database, rows = _indexed_library(tmp_path)
    root = tmp_path / "papers"
    selection = tmp_path / "selection.jsonl"
    config = tmp_path / "sources.yaml"
    alpha = root / "alpha.pdf"
    beta = root / "beta.pdf"
    old_alpha_sha, beta_sha = rows[0]["sha256"], rows[1]["sha256"]

    replacement = fitz.open()
    page = replacement.new_page()
    page.insert_text((40, 60), "alpha.pdf revised")
    page.insert_text((40, 100), "alpha revised-only evidence appears in this updated synthetic source.")
    replacement.save(alpha)
    replacement.close()
    stale_before_reconcile = handle(database, {"jsonrpc": "2.0", "id": 20,
                                               "method": "resources/read",
                                               "params": {"uri": f"papertrail://documents/{old_alpha_sha}"}})
    assert stale_before_reconcile["error"]["code"] == -32602
    stale = index_selection(database, config, selection, reconcile=True)
    assert any(issue["issue"] == "source_missing_or_changed" for issue in stale["issues"])
    assert old_alpha_sha not in {row["sha256"] for row in search_papers(
        database, "alpha-only-needle", Principal("local-dev"))}
    try:
        read_evidence(database, old_alpha_sha, 1, Principal("local-dev"))
    except ValueError as exc:
        assert str(exc) == "original paper not found"
    else:
        raise AssertionError("updated source left old citation readable")
    for uri in (f"papertrail://documents/{old_alpha_sha}",
                f"papertrail://evidence/{old_alpha_sha}/1"):
        stale_resource = handle(database, {"jsonrpc": "2.0", "id": 21,
                                           "method": "resources/read", "params": {"uri": uri}})
        assert stale_resource["error"]["code"] == -32602

    new_alpha_sha = hashlib.sha256(alpha.read_bytes()).hexdigest()
    selected_rows = [dict(rows[1]), dict(rows[0], sha256=new_alpha_sha)]
    selection.write_text("".join(json.dumps(row) + "\n" for row in selected_rows), encoding="utf-8")
    assert index_selection(database, config, selection, reconcile=True)["added"] == 1
    assert "alpha revised-only evidence" in read_evidence(
        database, new_alpha_sha, 1, Principal("local-dev"))["text"]

    beta.unlink()
    for uri in (f"papertrail://documents/{beta_sha}",
                f"papertrail://evidence/{beta_sha}/1"):
        stale_deleted_source = handle(database, {"jsonrpc": "2.0", "id": 30,
                                                 "method": "resources/read", "params": {"uri": uri}},
                                      Principal("user-b"))
        assert stale_deleted_source["error"]["code"] == -32602
    deleted = index_selection(database, config, selection, reconcile=True)
    assert any(issue["issue"] == "source_missing_or_changed" for issue in deleted["issues"])
    assert beta_sha not in {row["sha256"] for row in search_papers(
        database, "beta-only-needle", Principal("user-b"))}
    mcp_read = handle(database, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"name": "get_evidence", "arguments": {
                                     "sha256": beta_sha, "page": 1}}}, Principal("user-b"))
    assert mcp_read["result"]["isError"] is True
    for uri in (f"papertrail://documents/{beta_sha}",
                f"papertrail://evidence/{beta_sha}/1"):
        deleted_resource = handle(database, {"jsonrpc": "2.0", "id": 31,
                                             "method": "resources/read", "params": {"uri": uri}},
                                  Principal("user-b"))
        assert deleted_resource["error"]["code"] == -32602
    client = create_app(database).test_client()
    assert client.get(f"/api/evidence/{beta_sha}/1",
                      environ_overrides={"papertrail.principal": Principal("user-b")}).status_code == 404
