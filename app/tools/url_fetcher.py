"""URL fetcher: validate -> fetch (timeout, size cap) -> extract readable text."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.tool_result import ErrorType, ToolResult
from app.tools.base import USER_AGENT, Tool, classify_http_error

_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
MIN_TEXT_CHARS = 200


def validate_url(url: str) -> str | None:
    """Return None if the URL is acceptable, otherwise a reason string."""
    if not isinstance(url, str) or not url.strip():
        return "URL is empty"
    if len(url) > 2048:
        return "URL is too long"
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return "URL could not be parsed"
    if parsed.scheme not in ("http", "https"):
        return f"unsupported scheme '{parsed.scheme or '(none)'}'"
    host = (parsed.hostname or "").lower()
    if not host or "." not in host and host not in _BLOCKED_HOSTS:
        return "URL has no valid host"
    if host in _BLOCKED_HOSTS:
        return "local/internal hosts are not allowed"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return "private/internal IP addresses are not allowed"
    except ValueError:
        pass  # hostname, not an IP literal
    return None


def extract_text(markup: str) -> tuple[str, str]:
    """Return (title, readable text) from HTML, dropping scripts and page chrome."""
    soup = BeautifulSoup(markup, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "")[:200]
    for tag in soup(["title", "script", "style", "noscript", "nav", "footer", "header",
                     "aside", "form", "svg", "iframe"]):
        tag.decompose()
    lines = (re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").splitlines())
    text = "\n".join(ln for ln in lines if len(ln) >= 30)
    return title, text


class UrlFetcherTool(Tool):
    name = "url_fetcher"

    def __init__(
        self, client: httpx.Client | None = None, timeout: float = 10.0,
        max_bytes: int = 2_000_000, max_chars: int = 8000,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self.max_bytes, self.max_chars = max_bytes, max_chars

    def _run(self, url: str = "", **_: Any) -> ToolResult:
        reason = validate_url(url)
        if reason:
            return ToolResult.fail(self.name, ErrorType.INVALID_INPUT, f"invalid URL: {reason}",
                                   retryable=False, url=url)
        try:
            with self._client.stream("GET", url) as resp:
                resp.raise_for_status()
                final_url = str(resp.url)
                if (redirect_reason := validate_url(final_url)):
                    return ToolResult.fail(self.name, ErrorType.INVALID_INPUT,
                                           f"redirected to disallowed URL: {redirect_reason}",
                                           retryable=False, url=url)
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and not ctype.startswith(_TEXT_TYPES):
                    return ToolResult.fail(self.name, ErrorType.UNSUPPORTED_CONTENT,
                                           f"unsupported content type '{ctype}'",
                                           retryable=False, url=url)
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) >= self.max_bytes:
                        break
                encoding = resp.encoding or "utf-8"
        except Exception as e:
            etype, msg, retryable = classify_http_error(e)
            return ToolResult.fail(self.name, etype, msg, retryable=retryable, url=url)

        markup = body.decode(encoding, errors="replace")
        if ctype == "text/plain":
            title, text = "", markup
        else:
            title, text = extract_text(markup)
        if len(text) < MIN_TEXT_CHARS:
            return ToolResult.fail(self.name, ErrorType.EMPTY,
                                   f"page had too little readable text ({len(text)} chars)",
                                   retryable=False, url=url)
        truncated = len(text) > self.max_chars
        return ToolResult.ok(
            self.name,
            {"url": final_url, "title": title, "text": text[: self.max_chars],
             "chars": len(text), "truncated": truncated},
            url=url,
        )
