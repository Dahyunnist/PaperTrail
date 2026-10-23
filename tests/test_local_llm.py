import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from papertrail.local_llm import ModelResponseTruncated, chat_json


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


def test_openai_compatible_client_enforces_model_budget_and_redacts_key(tmp_path, monkeypatch):
    seen = {}
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "{\"ok\":true}"}}],
                               "usage": {"prompt_tokens": 100, "completion_tokens": 20}}).encode()

    ledger = tmp_path / "budget.json"
    monkeypatch.setenv("PAPERTRAIL_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("PAPERTRAIL_OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("PAPERTRAIL_OPENAI_API_KEY_ENV", "TEST_DEEPSEEK_KEY")
    monkeypatch.setenv("TEST_DEEPSEEK_KEY", "secret-test-key")
    monkeypatch.setenv("PAPERTRAIL_LLM_BUDGET_FILE", str(ledger))
    monkeypatch.setenv("PAPERTRAIL_LLM_BUDGET_USD", "0.50")
    import papertrail.local_llm as llm
    def mock_open(request, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["payload"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(llm, "urlopen", mock_open)
    result = chat_json("deepseek-flash", "system", "prompt")
    assert result["ok"] is True
    assert result["_usage"]["prompt_eval_count"] == 100
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["authorization"] == "Bearer secret-test-key"
    assert seen["payload"]["max_tokens"] == 800
    assert seen["payload"]["temperature"] == 0.0
    assert "secret-test-key" not in ledger.read_text(encoding="utf-8")
    ledger.write_text('{"spent_upper_bound_usd": 0.4999, "requests": []}', encoding="utf-8")
    seen.clear()
    import pytest
    with pytest.raises(RuntimeError, match="budget cap"):
        chat_json("deepseek-flash", "system", "prompt")
    assert not seen


def test_openai_compatible_client_marks_length_limited_json_and_records_usage(tmp_path, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self):
            return json.dumps({
                "choices": [{"finish_reason": "length", "message": {"content": "{\\\"claims\\\":"}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 800},
            }).encode()

    ledger = tmp_path / "budget.json"
    monkeypatch.setenv("PAPERTRAIL_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("PAPERTRAIL_OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("PAPERTRAIL_OPENAI_API_KEY_ENV", "TEST_DEEPSEEK_KEY")
    monkeypatch.setenv("TEST_DEEPSEEK_KEY", "test-key")
    monkeypatch.setenv("PAPERTRAIL_LLM_BUDGET_FILE", str(ledger))
    monkeypatch.setenv("PAPERTRAIL_LLM_BUDGET_USD", "0.50")
    import papertrail.local_llm as llm
    monkeypatch.setattr(llm, "urlopen", lambda *_args, **_kwargs: Response())

    import pytest
    with pytest.raises(ModelResponseTruncated, match="finish_reason=length") as caught:
        chat_json("deepseek-flash", "system", "prompt")

    assert caught.value.usage["prompt_eval_count"] == 120
    assert json.loads(ledger.read_text(encoding="utf-8"))["requests"][0]["completion_tokens"] == 800


def test_one_qa_turn_blocks_model_call_17_before_network(monkeypatch):
    import pytest
    import papertrail.local_llm as llm

    monkeypatch.setenv("PAPERTRAIL_LLM_PROVIDER", "ollama")
    with llm.model_turn_budget() as budget:
        for _ in range(16):
            llm._reserve_turn_call("system", "prompt")
        with pytest.raises(RuntimeError, match="QA turn model-call budget"):
            llm._reserve_turn_call("system", "prompt")
    assert budget["calls"] == 16


def test_one_hosted_qa_turn_reserves_peak_cost_before_call(monkeypatch):
    import pytest
    import papertrail.local_llm as llm

    monkeypatch.setenv("PAPERTRAIL_LLM_PROVIDER", "openai-compatible")
    with llm.model_turn_budget() as budget:
        for _ in range(12):
            llm._reserve_turn_call("s" * 100, "p" * 2_200)
        with pytest.raises(RuntimeError, match="QA turn model-cost budget"):
            llm._reserve_turn_call("s" * 100, "p" * 2_200)
    assert budget["reserved_usd"] <= 0.05
