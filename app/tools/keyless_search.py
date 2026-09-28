"""Keyless web-search providers: no account, API key or login required.

* DuckDuckGoProvider  - DuckDuckGo's lightweight HTML endpoint (general web results).
* BingRssProvider     - Bing's public RSS output, for web results or news results.

Both parse public HTML/RSS, so they are more fragile than an API. That is
acceptable because they sit behind the same validator and recovery chain:
if DuckDuckGo returns a bot-check page (zero parsable results), the validator
reports an empty result and the agent falls back to Bing, and so on.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.tool_result import ErrorType
from app.tools.base import USER_AGENT, classify_http_error
from app.tools.web_search import ProviderError, SearchProvider


def _get(client: httpx.Client, method: str, url: str, **kw: Any) -> httpx.Response:
    try:
        resp = client.request(method, url, **kw)
        resp.raise_for_status()
        return resp
    except Exception as e:
        etype, msg, retryable = classify_http_error(e)
        raise ProviderError(etype, msg, retryable) from e


def _unwrap_redirect(href: str, param: str) -> str:
    """Search engines wrap result links in redirects; return the real target URL."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    target = parse_qs(parsed.query).get(param)
    return unquote(target[0]) if target else href


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"
    URL = "https://html.duckduckgo.com/html/"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 10.0) -> None:
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        resp = _get(self._client, "POST", self.URL, data={"q": query, "kl": "us-en"})
        return self.parse(resp.text, max_results)

    @staticmethod
    def parse(markup: str, max_results: int) -> list[dict[str, Any]]:
        soup = BeautifulSoup(markup, "html.parser")
        results: list[dict[str, Any]] = []
        for block in soup.select("div.result"):
            if "result--ad" in (block.get("class") or []):
                continue  # skip sponsored results
            link = block.select_one("a.result__a")
            if link is None or not link.get("href"):
                continue
            snippet = block.select_one(".result__snippet")
            results.append({
                "title": link.get_text(" ", strip=True),
                "url": _unwrap_redirect(str(link["href"]), "uddg"),
                "snippet": snippet.get_text(" ", strip=True) if snippet else "",
            })
            if len(results) >= max_results:
                break
        return results  # empty list => validator reports EMPTY => fallback provider


class BingRssProvider(SearchProvider):
    """Bing search results as RSS. kind="web" or kind="news" (recent articles)."""

    def __init__(self, kind: str = "web", client: httpx.Client | None = None,
                 timeout: float = 10.0) -> None:
        if kind not in ("web", "news"):
            raise ValueError("kind must be 'web' or 'news'")
        self.kind = kind
        self.name = f"bing-{kind}-rss"
        self.url = ("https://www.bing.com/news/search" if kind == "news"
                    else "https://www.bing.com/search")
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        resp = _get(self._client, "GET", self.url,
                    params={"q": query, "format": "rss", "setlang": "en-US"})
        return self.parse(resp.text, max_results)

    @staticmethod
    def parse(xml_text: str, max_results: int) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(xml_text.strip())
        except ET.ParseError as e:
            raise ProviderError(ErrorType.MALFORMED, f"Bing RSS was not valid XML ({e})") from e
        results: list[dict[str, Any]] = []
        for item in root.iter("item"):
            link = (item.findtext("link") or "").strip()
            if not link:
                continue
            desc = BeautifulSoup(item.findtext("description") or "", "html.parser")
            results.append({
                "title": (item.findtext("title") or "").strip(),
                "url": _unwrap_redirect(link, "url"),  # news links go via apiclick.aspx
                "snippet": desc.get_text(" ", strip=True),
            })
            if len(results) >= max_results:
                break
        return results
