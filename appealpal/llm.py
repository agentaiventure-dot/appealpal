"""OpenAI-compatible chat client, standard library only, with an origin allowlist so the key cannot leak."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict
from urllib.parse import urlparse

ALLOWED_ORIGINS = ("https://api.groq.com", "https://api.tokenfactory.nebius.com", "https://api.openai.com")
LOOPBACK = ("127.0.0.1", "localhost", "::1")


class LLMError(RuntimeError):
    pass


def check_base(base_url: str, allow_local: bool) -> str:
    p = urlparse(base_url)
    origin = f"{p.scheme}://{p.netloc}"
    if p.query or p.fragment or p.username or p.password:
        raise LLMError("base URL must not carry credentials or query strings")
    if origin in ALLOWED_ORIGINS or (allow_local and p.scheme == "http" and p.hostname in LOOPBACK):
        return base_url.rstrip("/")
    raise LLMError(f"refusing to send the API key to {origin!r}; allowed: {', '.join(ALLOWED_ORIGINS)} or a loopback server")


class ChatClient:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 120, allow_local: bool = False):
        if not api_key:
            raise LLMError("LLM_API_KEY is not set")
        self.api_key, self.base, self.model, self.timeout = api_key, check_base(base_url, allow_local), model, timeout
        self.last_usage: Dict[str, Any] = {}

    @classmethod
    def from_env(cls) -> "ChatClient":
        return cls(os.environ.get("LLM_API_KEY", ""), os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai"),
                   os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"), allow_local=os.environ.get("APPEALPAL_ALLOW_LOCAL") == "1")

    def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        body = {"model": self.model, "temperature": 0.0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}"); req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise LLMError(f"LLM call failed: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}") from None
        except urllib.error.URLError as e:
            raise LLMError(f"LLM unreachable: {e.reason}") from None
        self.last_usage = out.get("usage") or {}
        try:
            text = out["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("no completion content")
        text = text.strip().strip("`")
        if text.startswith("json"):
            text = text[4:]
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            s, e = text.find("{"), text.rfind("}")
            if s < 0 or e < 0:
                raise LLMError("model output is not JSON")
            obj = json.loads(text[s:e + 1])
        if not isinstance(obj, dict):
            raise LLMError("model output is not a JSON object")
        return obj
