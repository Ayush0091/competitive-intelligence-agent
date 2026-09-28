"""Offline mode: a synthetic search provider + an httpx MockTransport serving
synthetic pages, both backed by data/synthetic_corpus.json.

All companies and figures in that corpus are FICTIONAL. Offline mode exists so
the full agent pipeline (real UrlFetcherTool, real validator, real recovery)
can run without network access or API keys. One page deliberately returns
HTTP 503 so the fetch-fallback path is exercised organically.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.tools.web_search import SearchProvider

CORPUS_PATH = Path(__file__).resolve().parents[2] / "data" / "synthetic_corpus.json"
SYNTHETIC_TAG = "[SYNTHETIC] "

_STOP = {"the", "a", "an", "of", "in", "and", "for", "to", "vs", "on", "with", "market",
         "recent", "latest", "is", "its", "by", "from"}
# Domain words that alone should not make a document relevant to a query.
_GENERIC = {"ai", "accelerator", "chip", "revenue", "share", "competitor", "development",
            "new", "announcement", "compan", "industry", "sector", "semiconductor"}


def _tokens(text: str) -> set[str]:
    toks = set()
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if t in _STOP:
            continue
        toks.add(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return toks


def load_corpus(path: Path = CORPUS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class SyntheticSearchProvider(SearchProvider):
    def __init__(self, corpus: dict[str, Any] | None = None, name: str = "synthetic") -> None:
        self.corpus = corpus or load_corpus()
        self.name = name
        self.base = self.corpus["base_url"]

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        q = _tokens(query)
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for idx, doc in enumerate(self.corpus["documents"]):
            title_t = _tokens(doc["title"])
            body_t = _tokens(" ".join(doc["paragraphs"]) + " " + doc.get("snippet", ""))
            kw_t = _tokens(" ".join(doc.get("keywords", [])))
            distinctive = (q - _GENERIC) & (title_t | body_t | kw_t)
            if not distinctive:
                continue
            score = sum(2.0 if t in title_t else 1.0 if t in kw_t else 0.5
                        for t in q if t in (title_t | body_t | kw_t))
            scored.append((score, -idx, doc))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        out = []
        for _, _, doc in scored[:max_results]:
            snippet = doc.get("snippet") or " ".join(doc["paragraphs"][:1])
            out.append({"title": SYNTHETIC_TAG + doc["title"], "url": self.base + doc["slug"],
                        "snippet": snippet})
        return out


def synthetic_transport(corpus: dict[str, Any] | None = None) -> httpx.MockTransport:
    corpus = corpus or load_corpus()
    docs = {d["slug"]: d for d in corpus["documents"]}

    def handler(request: httpx.Request) -> httpx.Response:
        slug = request.url.path.strip("/")
        doc = docs.get(slug)
        if doc is None:
            return httpx.Response(404, text="not found")
        status = doc.get("status", 200)
        if status != 200:
            return httpx.Response(status, text="upstream unavailable")
        body = "".join(f"<p>{html.escape(p)}</p>" for p in doc["paragraphs"])
        page = (f"<html><head><title>{html.escape(SYNTHETIC_TAG + doc['title'])}</title>"
                f"<script>var tracking=1;</script></head><body><nav>Home | News | About us"
                f" navigation links here</nav><article><h1>{html.escape(doc['title'])}</h1>"
                f"{body}</article><footer>Synthetic footer text that should be removed.</footer>"
                f"</body></html>")
        return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})

    return httpx.MockTransport(handler)
