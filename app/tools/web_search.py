"""Web search tool with swappable providers.

web_search(query) -> ToolResult(data={"results": [{"title","url","snippet"}], "provider": ...})

Providers:
  * TavilyProvider    – web search API (needs TAVILY_API_KEY)
  * WikipediaProvider – keyless API, but needs AGENT_CONTACT (Wikimedia 403s anonymous clients)
  * DuckDuckGoProvider / BingRssProvider (keyless_search.py) – default, no key or login
  * SyntheticSearchProvider (app/tools/synthetic.py) – offline test corpus
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import quote

import httpx

from app.models.tool_result import ErrorType, ToolResult
from app.tools.base import USER_AGENT, Tool, classify_http_error, user_agent


class ProviderError(Exception):
    def __init__(self, error_type: ErrorType, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.error_type, self.retryable = error_type, retryable


class SearchProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Return a list of {"title","url","snippet"} dicts or raise ProviderError."""


def _request_json(client: httpx.Client, method: str, url: str, **kw: Any) -> Any:
    try:
        resp = client.request(method, url, **kw)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        etype, msg, retryable = classify_http_error(e)
        raise ProviderError(etype, msg, retryable) from e


class TavilyProvider(SearchProvider):
    name = "tavily"
    URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, client: httpx.Client | None = None, timeout: float = 10.0):
        if not api_key:
            raise ValueError("TavilyProvider requires an API key")
        self._key = api_key
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        payload = {"query": query, "max_results": max_results, "search_depth": "basic"}
        data = _request_json(self._client, "POST", self.URL, json=payload,
                             headers={"Authorization": f"Bearer {self._key}"})
        if not isinstance(data, dict) or "results" not in data:
            raise ProviderError(ErrorType.MALFORMED, 'Tavily response missing "results"')
        if not isinstance(data["results"], list):
            raise ProviderError(ErrorType.MALFORMED, 'Tavily "results" is not a list')
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data["results"] if isinstance(r, dict)
        ]


_TAG_RE = re.compile(r"<[^>]+>")


class WikipediaProvider(SearchProvider):
    """Keyless, but Wikimedia returns HTTP 403 unless the User-Agent carries operator
    contact info (email or URL) - so it is only enabled when AGENT_CONTACT is set."""

    name = "wikipedia"
    URL = "https://en.wikipedia.org/w/api.php"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 10.0,
                 contact: str | None = None):
        self._client = client or httpx.Client(
            timeout=timeout, headers={"User-Agent": user_agent(contact)})

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        params = {"action": "query", "list": "search", "srsearch": query, "format": "json",
                  "srlimit": max_results, "utf8": 1}
        data = _request_json(self._client, "GET", self.URL, params=params)
        try:
            items = data["query"]["search"]
        except (KeyError, TypeError) as e:
            raise ProviderError(ErrorType.MALFORMED, f"Wikipedia response missing {e}") from e
        return [
            {
                "title": it.get("title", ""),
                "url": "https://en.wikipedia.org/wiki/" + quote(it.get("title", "").replace(" ", "_")),
                "snippet": html.unescape(_TAG_RE.sub("", it.get("snippet", ""))),
            }
            for it in items if isinstance(it, dict)
        ]


class WebSearchTool(Tool):
    name = "web_search"

    def __init__(self, provider: SearchProvider, max_results: int = 5) -> None:
        self.provider = provider
        self.max_results = max_results

    def describe(self) -> str:
        return f"web_search[{self.provider.name}]"

    def _run(self, query: str = "", max_results: int | None = None, **_: Any) -> ToolResult:
        query = (query or "").strip()
        if not query or len(query) > 400:
            return ToolResult.fail(self.name, ErrorType.INVALID_INPUT,
                                   "query must be 1-400 characters", retryable=False)
        n = max(1, min(max_results or self.max_results, 10))
        try:
            results = self.provider.search(query, n)
        except ProviderError as e:
            return ToolResult.fail(self.name, e.error_type, str(e), retryable=e.retryable,
                                   provider=self.provider.name)
        return ToolResult.ok(self.name, {"results": results[:n], "provider": self.provider.name},
                             provider=self.provider.name, query=query)
