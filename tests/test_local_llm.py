import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from papertrail.local_llm import chat_json


def test_local_chat_client_uses_loopback_ollama_json_api(monkeypatch):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["payload"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            body = json.dumps({"message": {"content": "{\"ok\":true}"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("PAPERTRAIL_OLLAMA_URL", f"http://127.0.0.1:{server.server_port}")
    try:
        result = chat_json("local-test-model", "system", "prompt")
    finally:
        server.shutdown()
        thread.join(timeout=2)
    assert result["ok"] is True
    assert result["_usage"]["eval_count"] is None
    assert seen["path"] == "/api/chat"
    assert seen["payload"]["model"] == "local-test-model"
    assert seen["payload"]["format"] == "json"
