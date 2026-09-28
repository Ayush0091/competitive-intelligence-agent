"""Settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "openai": "gpt-4o-mini", "ollama": "auto"}
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "none"  # ollama | anthropic | openai | none
    llm_model: str | None = None
    llm_api_key: str | None = field(default=None, repr=False)
    llm_base_url: str | None = None
    llm_timeout_s: float = 120.0
    ollama_num_ctx: int = 8192
    ollama_think: bool = False
    tavily_api_key: str | None = field(default=None, repr=False)
    search_provider: str = "auto"  # auto | tavily | duckduckgo | bing | wikipedia
    agent_contact: str | None = None  # email/URL for the User-Agent (needed by Wikipedia)
    http_timeout_s: float = 10.0
    max_retries: int = 1
    retry_backoff_s: float = 0.5
    max_sources: int = 6
    max_page_chars: int = 8000

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> "Settings":
        if load_env_file and not os.getenv("CI_AGENT_SKIP_DOTENV"):  # tests set this
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:  # python-dotenv is optional at runtime
                pass

        provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
        anthropic_key = os.getenv("ANTHROPIC_API_KEY") or None
        openai_key = os.getenv("OPENAI_API_KEY") or None
        ollama_model = os.getenv("OLLAMA_MODEL") or None
        if not provider:
            provider = ("ollama" if ollama_model else "anthropic" if anthropic_key
                        else "openai" if openai_key else "none")
        # Ollama runs locally and needs no key; the others do.
        key = {"anthropic": anthropic_key, "openai": openai_key, "ollama": "local"}.get(provider)
        if provider != "none" and not key:
            provider = "none"  # asked for a provider but no key: degrade, don't crash

        if provider == "ollama":
            model = ollama_model or os.getenv("LLM_MODEL") or DEFAULT_MODELS["ollama"]
            base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv("LLM_BASE_URL") or DEFAULT_OLLAMA_URL
            default_timeout = 300.0  # local models on consumer hardware can be slow
        else:
            model = os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider)
            base_url = os.getenv("LLM_BASE_URL") or None
            default_timeout = 120.0

        return cls(
            llm_provider=provider,
            llm_model=model,
            llm_api_key=key if provider != "ollama" else None,
            llm_base_url=base_url,
            llm_timeout_s=max(5.0, _float("LLM_TIMEOUT_S", default_timeout)),
            ollama_num_ctx=max(2048, _int("OLLAMA_NUM_CTX", 8192)),
            ollama_think=(os.getenv("OLLAMA_THINK") or "false").strip().lower() in ("1", "true", "yes"),
            tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
            agent_contact=(os.getenv("AGENT_CONTACT") or "").strip() or None,
            search_provider=(os.getenv("SEARCH_PROVIDER") or "auto").lower(),
            http_timeout_s=_float("HTTP_TIMEOUT_S", 10.0),
            max_retries=max(0, _int("MAX_RETRIES", 1)),
            retry_backoff_s=max(0.0, _float("RETRY_BACKOFF_S", 0.5)),
            max_sources=max(1, _int("MAX_SOURCES", 6)),
            max_page_chars=max(1000, _int("MAX_PAGE_CHARS", 8000)),
        )

    def secrets(self) -> list[str]:
        """Values that must never appear in logs."""
        return [s for s in (self.llm_api_key, self.tavily_api_key) if s]
