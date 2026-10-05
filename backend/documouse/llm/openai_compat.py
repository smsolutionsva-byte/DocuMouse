"""Provider for any OpenAI-compatible Chat Completions endpoint.

That covers Groq, OpenRouter, Ollama, LM Studio, vLLM, llama.cpp server and
many more, which is why it's the only implementation the MVP needs.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .base import LLMError


class OpenAICompatibleProvider:
    def __init__(self, *, name: str, base_url: str, model: str, api_key: str | None, timeout: float = 60.0):
        self.name = name
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._timeout = timeout

    def complete_json(self, system: str, user: str, *, max_tokens: int = 2000) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            response = httpx.post(self._url, headers=self._headers, json=payload, timeout=self._timeout)
            if response.status_code == 400 and "response_format" in response.text:
                # Some local servers don't support JSON mode; the prompt still asks for JSON.
                payload.pop("response_format")
                response = httpx.post(self._url, headers=self._headers, json=payload, timeout=self._timeout)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"{self.name} request failed: {exc}") from exc
        return parse_json_object(content)


def parse_json_object(content: str) -> dict[str, Any]:
    content = content.strip()
    # Tolerate ```json fences and reasoning preambles from smaller local models.
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.S)
    if fenced:
        content = fenced.group(1)
    elif not content.startswith("{"):
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1:
            raise LLMError("The model did not return JSON.")
        content = content[start : end + 1]
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"The model returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("The model returned JSON that is not an object.")
    return value
