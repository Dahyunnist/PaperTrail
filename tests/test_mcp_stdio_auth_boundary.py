import hashlib
import json
import subprocess
import sys

import fitz
import yaml

from papertrail.access import assign_version_to_collection, create_collection
from papertrail.s1_index import index_selection, open_database


def _stdio_process(database, principal_id=None):
    if principal_id is None:
        command = [sys.executable, "-m", "papertrail.mcp_server", "--db", str(database)]
    else:
        bootstrap = (
            "import sys; from pathlib import Path; "
            "from papertrail.access import Principal; "
            "from papertrail.mcp_server import main; "
            "main(Path(sys.argv[1]), principal=Principal(sys.argv[2]))"
        )
        command = [sys.executable, "-c", bootstrap, str(database), principal_id]
    return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8")


def _call(process, request_id, method, params=None):
    request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    assert line, process.stderr.read()
    return json.loads(line)


def _stop(process):
    process.terminate()
    process.wait(timeout=5)


def test_stdio_transport_fails_closed_without_trusted_principal_and_scopes_injected_users(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    sources = [
        ("owner-a.pdf", "OwnerAOnlyneedle belongs to owner A."),
        ("owner-b.pdf", "OwnerBOnlyneedle belongs to owner B."),
    ]
    selection_rows = []
    for filename, body in sources:
        pdf = root / filename
        document = fitz.open()
        page = document.new_page()
        page.insert_text((40, 60), body)
        document.save(pdf)
        document.close()
        selection_rows.append({
            "root_id": "synthetic", "file_name": filename, "relative_path": filename,
            "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "kind": "pdf",
            "source_type": "original_pdf",
        })

    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "synthetic", "path": str(root)}]}),
                      encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text("".join(json.dumps(row) + "\n" for row in selection_rows), encoding="utf-8")
    database = tmp_path / "library.sqlite3"
    index_selection(database, config, selection)
    create_collection(database, "owner-a-collection", "owner-a")
    create_collection(database, "owner-b-collection", "owner-b")
    conn = open_database(database)
    try:
        versions = {row["sha256"]: row["version_id"] for row in conn.execute(
            "SELECT version_id,sha256 FROM paper_versions")}
    finally:
        conn.close()
    assign_version_to_collection(database, versions[selection_rows[0]["sha256"]], "owner-a-collection")
    owner_b_version = versions[selection_rows[1]["sha256"]]
    assign_version_to_collection(database, owner_b_version, "owner-b-collection")
    owner_a_sha, owner_b_sha = (row["sha256"] for row in selection_rows)

    anonymous = _stdio_process(database)
    try:
        search = _call(anonymous, 1, "tools/call", {"name": "search_papers", "arguments": {
            "query": "OwnerBOnlyneedle"}, "user_id": "owner-b"})
        resources = _call(anonymous, 2, "resources/list", {"user_id": "owner-b"})
        read = _call(anonymous, 3, "resources/read", {
            "uri": f"papertrail://evidence/{owner_b_sha}/1", "user_id": "owner-b"})
        assert [search["error"]["code"], resources["error"]["code"],
                read["error"]["code"]] == [-32001, -32001, -32001]
    finally:
        _stop(anonymous)

    owner_a = _stdio_process(database, "owner-a")
    try:
        own = _call(owner_a, 1, "tools/call", {"name": "get_evidence", "arguments": {
            "sha256": owner_a_sha, "page": 1}})
        foreign = _call(owner_a, 2, "tools/call", {"name": "get_evidence", "arguments": {
            "sha256": owner_b_sha, "page": 1}, "user_id": "owner-b"})
        assert "OwnerAOnlyneedle" in own["result"]["structuredContent"]["text"]
        assert foreign["result"]["isError"] is True
        resources = _call(owner_a, 3, "resources/list")["result"]["resources"]
        assert {item["uri"] for item in resources} == {f"papertrail://documents/{owner_a_sha}"}
        own_resource = _call(owner_a, 4, "resources/read", {
            "uri": f"papertrail://evidence/{owner_a_sha}/1"})
        foreign_resource = _call(owner_a, 5, "resources/read", {
            "uri": f"papertrail://evidence/{owner_b_sha}/1"})
        assert "OwnerAOnlyneedle" in own_resource["result"]["contents"][0]["text"]
        assert foreign_resource["error"]["code"] == -32602
    finally:
        _stop(owner_a)

    owner_b = _stdio_process(database, "owner-b")
    try:
        own = _call(owner_b, 1, "tools/call", {"name": "get_evidence", "arguments": {
            "sha256": owner_b_sha, "page": 1}})
        foreign = _call(owner_b, 2, "tools/call", {"name": "get_evidence", "arguments": {
            "sha256": owner_a_sha, "page": 1}, "user_id": "owner-a"})
        assert "OwnerBOnlyneedle" in own["result"]["structuredContent"]["text"]
        assert foreign["result"]["isError"] is True
        resources = _call(owner_b, 3, "resources/list")["result"]["resources"]
        assert {item["uri"] for item in resources} == {f"papertrail://documents/{owner_b_sha}"}
        own_resource = _call(owner_b, 4, "resources/read", {
            "uri": f"papertrail://documents/{owner_b_sha}"})
        foreign_resource = _call(owner_b, 5, "resources/read", {
            "uri": f"papertrail://documents/{owner_a_sha}"})
        assert owner_b_sha in own_resource["result"]["contents"][0]["text"]
        assert foreign_resource["error"]["code"] == -32602
    finally:
        _stop(owner_b)

    revised_pdf = root / "owner-a.pdf"
    revised = fitz.open()
    revised.new_page().insert_text((40, 60), "OwnerARevisedneedle replaces the original evidence.")
    revised.save(revised_pdf)
    revised.close()
    revised_sha = hashlib.sha256(revised_pdf.read_bytes()).hexdigest()
    stale = _stdio_process(database, "owner-a")
    try:
        resources = _call(stale, 1, "resources/list")["result"]["resources"]
        assert all(owner_a_sha not in item["uri"] for item in resources)
        expired = _call(stale, 2, "resources/read", {
            "uri": f"papertrail://evidence/{owner_a_sha}/1"})
        assert expired["error"]["code"] == -32602
    finally:
        _stop(stale)

    selection_rows[0]["sha256"] = revised_sha
    selection.write_text("".join(json.dumps(row) + "\n" for row in selection_rows), encoding="utf-8")
    index_selection(database, config, selection, reconcile=True)
    rebuilt = _stdio_process(database, "owner-a")
    try:
        resources = _call(rebuilt, 1, "resources/list")["result"]["resources"]
        assert {item["uri"] for item in resources} == {f"papertrail://documents/{revised_sha}"}
        revised_read = _call(rebuilt, 2, "resources/read", {
            "uri": f"papertrail://evidence/{revised_sha}/1"})
        old_read = _call(rebuilt, 3, "resources/read", {
            "uri": f"papertrail://evidence/{owner_a_sha}/1"})
        assert "OwnerARevisedneedle" in revised_read["result"]["contents"][0]["text"]
        assert old_read["error"]["code"] == -32602
    finally:
        _stop(rebuilt)
