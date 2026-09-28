"""Minimal LLM clients over raw HTTP (no vendor SDKs), behind one interface.

The LLM is used only for interpretation, planning, metric-expression extraction
and synthesis. Everything deterministic (tools, validation, retries, maths)
stays in Python.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Protocol

import httpx

from app.config import Settings


class LLMError(Exception):
    """Raised when the LLM call fails or returns unusable output."""


class TimedLLM:
    """Wraps any LLMClient and logs each call's latency - local models can be slow,
    so this makes the cost of the "brain" visible in the execution trace."""

    def __init__(self, inner: "LLMClient", log) -> None:
        self.inner, self._log = inner, log
        self.name = inner.name

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        purpose = system.split("\n", 1)[0][:60]
        start = time.perf_counter()
        try:
            out = self.inner.complete(system, prompt, max_tokens)
        except LLMError as e:
            self._log("LLM", f"{self.name} FAILED after {time.perf_counter() - start:.1f}s: {e}")
            raise
        self._log("LLM", f"{self.name} answered in {time.perf_counter() - start:.1f}s "
                         f"({len(out)} chars) - {purpose}")
        return out


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> str: ...


class AnthropicClient:
    def __init__(
        self, api_key: str, model: str, base_url: str | None = None,
        timeout: float = 60.0, client: httpx.Client | None = None,
    ) -> None:
        self.name = f"anthropic:{model}"
        self._key, self._model = api_key, model
        self._url = (base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01"}
        data = _post_json(self._client, self._url, body, headers)
        try:
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError) as e:
            raise LLMError(f"unexpected Anthropic response shape: {e}") from e


class OpenAICompatibleClient:
    """Works with OpenAI and any OpenAI-compatible endpoint (Groq, Together, Ollama...)."""

    def __init__(
        self, api_key: str, model: str, base_url: str | None = None,
        timeout: float = 60.0, client: httpx.Client | None = None,
    ) -> None:
        self.name = f"openai:{model}"
        self._key, self._model = api_key, model
        self._url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        data = _post_json(self._client, self._url, body, {"Authorization": f"Bearer {self._key}"})
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"unexpected OpenAI response shape: {e}") from e


class OllamaClient:
    """Local models via Ollama's native /api/chat endpoint.

    Uses Ollama's JSON mode (`format: "json"`), which constrains decoding to valid
    JSON - a big reliability win for small local models such as Qwen 7B/8B - and
    sets a larger context window than Ollama's default so source excerpts fit.
    """

    def __init__(
        self, model: str, base_url: str = "http://localhost:11434", timeout: float = 300.0,
        num_ctx: int = 8192, client: httpx.Client | None = None, think: bool = False,
    ) -> None:
        self.name = f"ollama:{model}"
        self._model, self._num_ctx, self._think = model, num_ctx, think
        self._base = base_url.rstrip("/")
        if self._base.endswith("/v1"):  # tolerate the OpenAI-compatible URL form
            self._base = self._base[: -len("/v1")]
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        body = {
            "model": self._model,
            "stream": False,
            "format": "json",
            # Reasoning models (Qwen3, DeepSeek-R1) otherwise spend minutes "thinking"
            # before every JSON answer; our prompts don't need it. Older Ollama
            # versions ignore this field.
            "think": self._think,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.2, "num_ctx": self._num_ctx,
                        "num_predict": max(512, max_tokens)},
        }
        try:
            data = _post_json(self._client, f"{self._base}/api/chat", body, {})
        except LLMError as e:
            if "ConnectError" in str(e):
                raise LLMError(f"Ollama not reachable at {self._base} - is Ollama running?") from e
            if "404" in str(e):
                raise LLMError(f"Ollama model '{self._model}' not found - run: "
                               f"ollama pull {self._model}") from e
            raise
        try:
            return data["message"]["content"] or ""
        except (KeyError, TypeError) as e:
            raise LLMError(f"unexpected Ollama response shape: {e}") from e

    def installed_models(self) -> list[str]:
        resp = self._client.get(f"{self._base}/api/tags", timeout=10)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", [])]

    def resolve_auto_model(self) -> str | None:
        """OLLAMA_MODEL=auto: pick an installed chat model, preferring Qwen."""
        try:
            names = [n for n in self.installed_models() if n and "embed" not in n.lower()]
        except Exception:  # noqa: BLE001 - server not reachable; check() will report it
            return None
        choice = next((n for n in names if "qwen" in n.lower()), names[0] if names else None)
        if choice:
            self._model, self.name = choice, f"ollama:{choice}"
        return choice

    def check(self) -> tuple[bool, str]:
        """Is the server up and is the model pulled? Returns (ok, human message)."""
        try:
            names = self.installed_models()
        except Exception as e:  # noqa: BLE001 - report any failure to the user
            return False, f"Ollama not reachable at {self._base} ({type(e).__name__})"
        wanted = self._model if ":" in self._model else f"{self._model}:latest"
        if wanted not in names and self._model not in names:
            return False, (f"model '{self._model}' not found in Ollama. Installed: "
                           f"{', '.join(names) or 'none'}")
        return True, f"Ollama OK at {self._base}; model '{self._model}' is installed"


def _post_json(client: httpx.Client, url: str, body: dict, headers: dict) -> dict[str, Any]:
    try:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException as e:
        raise LLMError("LLM request timed out") from e
    except httpx.HTTPStatusError as e:
        raise LLMError(f"LLM HTTP {e.response.status_code}") from e
    except (httpx.RequestError, ValueError) as e:
        raise LLMError(f"LLM request failed: {type(e).__name__}") from e


def build_llm(settings: Settings) -> LLMClient | None:
    if settings.llm_provider == "none" or not settings.llm_model:
        return None
    if settings.llm_provider == "ollama":
        client = OllamaClient(settings.llm_model, settings.llm_base_url or "http://localhost:11434",
                              timeout=settings.llm_timeout_s, num_ctx=settings.ollama_num_ctx,
                              think=settings.ollama_think)
        if settings.llm_model.lower() == "auto":
            client.resolve_auto_model()
        return client
    if not settings.llm_api_key:
        return None
    cls = AnthropicClient if settings.llm_provider == "anthropic" else OpenAICompatibleClient
    return cls(settings.llm_api_key, settings.llm_model, settings.llm_base_url,
               timeout=settings.llm_timeout_s)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM reply, tolerating code fences, prose and
    reasoning-model <think>...</think> blocks (e.g. Qwen3, DeepSeek-R1)."""
    text = _THINK.sub("", text or "")
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        cand = cand.strip()
        start, end = cand.find("{"), cand.rfind("}")
        if start == -1 or end <= start:
            continue
        try:
            obj = json.loads(cand[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise LLMError("no valid JSON object found in LLM output")
