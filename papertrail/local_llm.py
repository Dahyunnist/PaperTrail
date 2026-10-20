"""Small Ollama-compatible local chat client; no hosted fallback."""

from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen
from typing import Any


def configured_model() -> str | None:
    return os.environ.get("PAPERTRAIL_LLM_MODEL") or None


def chat_json(model: str, system: str, prompt: str) -> dict[str, Any]:
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
