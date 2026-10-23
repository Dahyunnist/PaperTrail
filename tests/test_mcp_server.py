import hashlib
import json
import os
import subprocess
import sys

import fitz
import yaml

from papertrail.s1_index import index_selection


def test_stdio_mcp_tools_and_resources_are_read_only(tmp_path):
    source = tmp_path / "paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "Evidence Server Paper", fontsize=16)
    page.insert_text((40, 100), "Semantic anchorword supports the measured evidence result on this page.")
    doc.save(source)
    doc.close()
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump({"roots": [{"id": "papers", "path": str(tmp_path)}]}), encoding="utf-8")
    selection = tmp_path / "selection.jsonl"
    selection.write_text(json.dumps({"root_id": "papers", "file_name": source.name,
        "relative_path": source.name, "sha256": sha, "kind": "pdf", "source_type": "original_pdf"}) + "\n",
        encoding="utf-8")
    db = tmp_path / "library.sqlite3"
    index_selection(db, config, selection)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    env = dict(os.environ, PAPERTRAIL_DB=str(db))
    proc = subprocess.Popen([sys.executable, "-m", "papertrail.mcp_server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)

    def call(request_id, method, params=None):
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method,
                                     "params": params or {}}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    try:
        initialized = call(1, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                               "clientInfo": {"name": "test-client", "version": "1"}})
        assert "tools" in initialized["result"]["capabilities"]
        proc.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        proc.stdin.flush()
        listed = call(2, "tools/list")
        assert {tool["name"] for tool in listed["result"]["tools"]} == {"search_papers", "get_evidence"}
        search_result = call(3, "tools/call", {"name": "search_papers", "arguments": {"query": "anchorword"}})
        hit = search_result["result"]["structuredContent"]["results"][0]
        assert hit["sha256"] == sha and hit["page"] == 1
        evidence = call(4, "tools/call", {"name": "get_evidence", "arguments": {"sha256": sha, "page": 1}})
        assert "anchorword" in evidence["result"]["structuredContent"]["text"]
        resources = call(5, "resources/list")
        uri = resources["result"]["resources"][0]["uri"]
        read = call(6, "resources/read", {"uri": uri})
        assert sha in read["result"]["contents"][0]["text"]
        invalid = call(7, "tools/call", {"name": "get_evidence", "arguments": {"sha256": sha, "page": 99}})
        assert invalid["result"]["isError"] is True
        outside = call(8, "tools/call", {"name": "get_evidence", "arguments": {
            "sha256": "0" * 64, "page": 1}})
        assert outside["result"]["isError"] is True
        unknown_resource = call(9, "resources/read", {"uri": f"papertrail://documents/{'0' * 64}"})
        assert unknown_resource["error"]["code"] == -32602
        assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    finally:
        proc.terminate()
        proc.wait(timeout=5)
