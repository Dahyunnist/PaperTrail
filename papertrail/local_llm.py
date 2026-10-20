"""Small Ollama-compatible local chat client; no hosted fallback."""

from __future__ import annotations

import json
import os
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

_BUDGET_LOCK = threading.Lock()
_FLASH_PEAK_INPUT_PER_M = 0.30
_FLASH_PEAK_OUTPUT_PER_M = 1.20
_MAX_PROMPT_CHARS = 2_400
_MAX_OUTPUT_TOKENS = 800
_MAX_BUDGET_USD = 0.50
_MAX_TOKENS_PER_CHAR = 4


def configured_model() -> str | None:
    return os.environ.get("PAPERTRAIL_LLM_MODEL") or None


def chat_json(model: str, system: str, prompt: str, *, thinking: bool | None = None) -> dict[str, Any]:
    if os.environ.get("PAPERTRAIL_LLM_PROVIDER", "ollama") == "openai-compatible":
        return _openai_compatible_json(model, system, prompt, thinking=thinking)
    base = os.environ.get("PAPERTRAIL_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    payload = json.dumps({"model": model, "stream": False, "format": "json",
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}]}, ensure_ascii=False).encode()
    request = Request(base + "/api/chat", data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=float(os.environ.get("PAPERTRAIL_LLM_TIMEOUT", "45"))) as response:
            result = json.loads(response.read())
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"本机模型调用失败：{type(exc).__name__}") from exc
    try:
        content = json.loads(result["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("本机模型没有返回有效 JSON") from exc
    if not isinstance(content, dict):
        raise RuntimeError("本机模型 JSON 顶层必须是对象")
    content["_usage"] = {key: result.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration")}
    return content


def _budget_file() -> Path:
    return Path(os.environ.get("PAPERTRAIL_LLM_BUDGET_FILE", ".local/p6-api-usage.json"))


def _max_request_cost(prompt_chars: int) -> float:
    prompt_token_ceiling = prompt_chars * _MAX_TOKENS_PER_CHAR
    return (prompt_token_ceiling * _FLASH_PEAK_INPUT_PER_M
            + _MAX_OUTPUT_TOKENS * _FLASH_PEAK_OUTPUT_PER_M) / 1_000_000


def _record_usage(model: str, prompt_chars: int, usage: dict[str, Any], reserved: float) -> dict[str, Any]:
    path = _budget_file()
    cap = min(_MAX_BUDGET_USD, float(os.environ.get("PAPERTRAIL_LLM_BUDGET_USD", _MAX_BUDGET_USD)))
    with _BUDGET_LOCK:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"cap_usd": cap, "spent_upper_bound_usd": 0.0, "requests": []}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
            cost = (prompt_tokens * _FLASH_PEAK_INPUT_PER_M + completion_tokens * _FLASH_PEAK_OUTPUT_PER_M) / 1_000_000
        else:
            cost = reserved
        data["spent_upper_bound_usd"] = round(data["spent_upper_bound_usd"] + cost, 8)
        data["requests"].append({"at": datetime.now(timezone.utc).isoformat(), "model": model,
                                 "prompt_chars": prompt_chars, "prompt_tokens": prompt_tokens,
                                 "completion_tokens": completion_tokens, "cost_upper_bound_usd": round(cost, 8)})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return {"prompt_eval_count": prompt_tokens, "eval_count": completion_tokens,
                "estimated_usd": round(cost, 8)}


def _openai_compatible_json(model: str, system: str, prompt: str,
                            *, thinking: bool | None = None) -> dict[str, Any]:
    system = system + "\nReturn a valid JSON object only."
    prompt_chars = len(system) + len(prompt)
    if prompt_chars > _MAX_PROMPT_CHARS:
        raise RuntimeError("Hosted prompt exceeds 2,400-character safety limit")
    reserved = _max_request_cost(prompt_chars)
    cap = min(_MAX_BUDGET_USD, float(os.environ.get("PAPERTRAIL_LLM_BUDGET_USD", _MAX_BUDGET_USD)))
    path = _budget_file()
    with _BUDGET_LOCK:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"spent_upper_bound_usd": 0.0}
        spent = float(data.get("spent_upper_bound_usd", 0.0))
    if spent + reserved > cap:
        raise RuntimeError("Hosted model budget cap reached; request blocked before sending")
    key_name = os.environ.get("PAPERTRAIL_OPENAI_API_KEY_ENV", "DEEPSEEK_API_KEY")
    api_key = os.environ.get(key_name)
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable: {key_name}")
    base = os.environ.get("PAPERTRAIL_OPENAI_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if base != "https://api.deepseek.com" or model != "deepseek-flash":
        raise RuntimeError("P6 budget profile only permits DeepSeek deepseek-flash at api.deepseek.com")
    payload = json.dumps({"model": model, "stream": False, "max_tokens": _MAX_OUTPUT_TOKENS,
                          "temperature": 0.0,
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}],
                          **({"thinking": {"type": "disabled" if not thinking else "enabled"}}
                             if thinking is not None else {})}, ensure_ascii=False).encode()
    request = Request(base + "/chat/completions", data=payload,
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    try:
        with urlopen(request, timeout=float(os.environ.get("PAPERTRAIL_LLM_TIMEOUT", "60"))) as response:
            result = json.loads(response.read())
    except HTTPError as exc:
        try:
            error_body = json.loads(exc.read())
            detail = error_body.get("error", {}).get("message", "")
            if not isinstance(detail, str):
                detail = ""
            detail = detail.replace(api_key, "[redacted]")[:180]
        except (json.JSONDecodeError, AttributeError, TypeError):
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"OpenAI-compatible model request failed: HTTP {exc.code}{suffix}") from None
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenAI-compatible model request failed: {type(exc).__name__}") from exc
    usage = result.get("usage", {})
    cost_data = _record_usage(model, prompt_chars, usage, reserved)
    try:
        choice = result["choices"][0]
        raw_content = choice["message"]["content"]
        if not isinstance(raw_content, str):
            raise TypeError("content is not text")
        content = json.loads(raw_content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        reason = result.get("choices", [{}])[0].get("finish_reason", "unknown") if result.get("choices") else "no_choice"
        length = len(raw_content) if "raw_content" in locals() and isinstance(raw_content, str) else 0
        raise RuntimeError(f"Hosted model did not return valid JSON (finish_reason={reason}, chars={length})") from exc
    if not isinstance(content, dict):
        raise RuntimeError("Hosted model JSON top-level must be an object")
    content["_usage"] = cost_data
    return content
