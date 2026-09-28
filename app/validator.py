"""Deterministic validation of every tool result. Nothing is trusted blindly."""

from __future__ import annotations

import math
import re
from typing import Callable

from app.models.report import CompetitorEntry, Finding, ReportBody
from app.models.tool_result import ErrorType, SearchHit, ToolResult, ValidationReport
from app.tools.url_fetcher import MIN_TEXT_CHARS, validate_url


_GENERIC_TERMS = {"ai", "the", "and", "market", "industry", "sector", "company", "companies",
                  "recent", "developments", "news", "latest", "analysis", "competitive",
                  "landscape", "compare", "comparison", "with", "from", "for", "of", "in"}


def relevance_terms(entities: list[str], market: str | None) -> set[str]:
    """Distinctive lowercase terms a relevant result should mention."""
    terms: set[str] = set()
    for phrase in list(entities) + ([market] if market else []):
        for tok in re.findall(r"[a-z0-9][a-z0-9\-]+", phrase.lower()):
            if tok not in _GENERIC_TERMS and len(tok) > 2:
                terms.add(tok[:-1] if tok.endswith("s") and len(tok) > 4 else tok)
    return terms


def is_relevant(hit: SearchHit, terms: set[str]) -> bool:
    """A search hit is relevant if its title, snippet or URL mentions any objective term.

    Search engines sometimes return generic popular pages for niche queries; fetching
    those wastes time and pollutes the evidence, so they are filtered before fetching.
    """
    if not terms:
        return True
    haystack = f"{hit.title} {hit.snippet} {hit.url}".lower()
    return any(t in haystack for t in terms)


_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def ungrounded_numbers(text: str, source_text: str) -> list[str]:
    """Figures in `text` that do not literally appear in `source_text`.

    Years (1900-2099) and single digits are ignored: they are usually context, not claims.
    """
    haystack = source_text.replace(",", "")
    missing = []
    for raw in _FIGURE.findall(text):
        num = raw.replace(",", "").rstrip(".")
        if len(num) < 2 or re.fullmatch(r"(19|20)\d\d", num):
            continue
        if not re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", haystack):
            missing.append(num)
    return missing


class ResultValidator:
    def __init__(self) -> None:
        self._by_tool: dict[str, Callable[[ToolResult], ValidationReport]] = {
            "web_search": self.validate_search,
            "url_fetcher": self.validate_fetch,
            "calculator": self.validate_calculation,
        }

    def validate(self, result: ToolResult) -> ValidationReport:
        if not isinstance(result, ToolResult):
            return ValidationReport.failed("tool did not return a ToolResult", ErrorType.MALFORMED)
        check = self._by_tool.get(result.tool)
        if check is None:
            return ValidationReport.failed(f"no validator for tool '{result.tool}'",
                                           ErrorType.UNKNOWN, retryable=False)
        return check(result)

    # --- shared -------------------------------------------------------------
    @staticmethod
    def _status_check(result: ToolResult) -> ValidationReport | None:
        if not result.success:
            err = result.error
            if err is None:
                return ValidationReport.failed("tool reported failure without an error",
                                               ErrorType.MALFORMED)
            return ValidationReport.failed(err.message, err.type, err.retryable)
        if not isinstance(result.data, dict):
            return ValidationReport.failed("tool reported success but returned no data",
                                           ErrorType.MALFORMED)
        return None

    # --- web search ---------------------------------------------------------
    def validate_search(self, result: ToolResult) -> ValidationReport:
        if (bad := self._status_check(result)) is not None:
            return bad
        data = result.data or {}
        if "results" not in data:
            return ValidationReport.failed('invalid tool response: missing "results"',
                                           ErrorType.MALFORMED)
        items = data["results"]
        if not isinstance(items, list):
            return ValidationReport.failed(
                f'invalid tool response: "results" is {type(items).__name__}, expected list',
                ErrorType.MALFORMED)
        if not items:
            # Re-running the identical query rarely helps; go straight to fallbacks
            # (secondary provider / simplified query).
            return ValidationReport.failed("search returned 0 results", ErrorType.EMPTY,
                                           retryable=False)
        hits, warnings = self._clean_hits(items)
        if not hits:
            return ValidationReport.failed(
                f"all {len(items)} results were malformed ({warnings[0] if warnings else ''})",
                ErrorType.MALFORMED)
        return ValidationReport.passed(warnings)

    @staticmethod
    def _clean_hits(items: list) -> tuple[list[SearchHit], list[str]]:
        hits: list[SearchHit] = []
        warnings: list[str] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                warnings.append(f"result {i} is not an object")
                continue
            url, title = item.get("url"), item.get("title")
            if not isinstance(url, str) or not isinstance(title, str):
                warnings.append(f"result {i} missing url/title")
                continue
            if (reason := validate_url(url)) is not None:
                warnings.append(f"result {i} has invalid url ({reason})")
                continue
            snippet = item.get("snippet") if isinstance(item.get("snippet"), str) else ""
            hits.append(SearchHit(title=title.strip() or url, url=url.strip(), snippet=snippet))
        return hits, warnings

    def search_hits(self, result: ToolResult) -> list[SearchHit]:
        """Return only the structurally valid hits of an already-validated result."""
        items = (result.data or {}).get("results") or []
        return self._clean_hits(items)[0] if isinstance(items, list) else []

    # --- url fetcher --------------------------------------------------------
    def validate_fetch(self, result: ToolResult) -> ValidationReport:
        if (bad := self._status_check(result)) is not None:
            return bad
        data = result.data or {}
        text = data.get("text")
        if not isinstance(text, str):
            return ValidationReport.failed('invalid tool response: missing "text"',
                                           ErrorType.MALFORMED)
        if len(text.strip()) < MIN_TEXT_CHARS:
            return ValidationReport.failed(f"page text too short ({len(text.strip())} chars)",
                                           ErrorType.EMPTY, retryable=False)
        url = data.get("url")
        if not isinstance(url, str) or validate_url(url):
            return ValidationReport.failed("fetched page has an invalid final URL",
                                           ErrorType.MALFORMED, retryable=False)
        warnings = ["content was truncated"] if data.get("truncated") else []
        return ValidationReport.passed(warnings)

    # --- synthesized report -------------------------------------------------
    @staticmethod
    def enforce_citations(
        body: ReportBody, valid_ids: set[int], source_texts: dict[int, str] | None = None
    ) -> tuple[ReportBody, list[str]]:
        """Strip citations to unknown sources; a 'fact' with no valid source becomes 'inference'.

        This is the guard against invented sources: the LLM can only cite sources
        the tools actually retrieved. When source texts are given, a 'fact' whose
        figures do not appear in any of its cited sources is also relabelled as
        'inference' (e.g. the agent's own computed value presented as sourced).
        """
        issues: list[str] = []
        groups: list[list[Finding] | list[CompetitorEntry]] = [
            body.recent_developments, body.market_signals, body.risks, body.competitors]
        for group in groups:
            for item in group:
                bad = [i for i in item.source_ids if i not in valid_ids]
                if bad:
                    issues.append(f"removed citation(s) to unknown source(s) {bad}")
                    item.source_ids = [i for i in item.source_ids if i in valid_ids]
                label = getattr(item, "text", None) or getattr(item, "summary", "") or ""
                if item.kind == "fact" and not item.source_ids:
                    item.kind = "inference"
                    issues.append(f"uncited 'fact' relabelled as inference: {label[:60]}")
                elif item.kind == "fact" and source_texts is not None:
                    cited = " ".join(source_texts.get(i, "") for i in item.source_ids)
                    missing = ungrounded_numbers(label, cited)
                    if missing:
                        item.kind = "inference"
                        issues.append(f"'fact' relabelled as inference - figure(s) {missing} not "
                                      f"in cited source(s): {label[:60]}")
        return body, issues

    # --- calculator ---------------------------------------------------------
    def validate_calculation(self, result: ToolResult) -> ValidationReport:
        if (bad := self._status_check(result)) is not None:
            return bad
        value = (result.data or {}).get("result")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return ValidationReport.failed("calculator result is not a number",
                                           ErrorType.MALFORMED, retryable=False)
        if not math.isfinite(value):
            return ValidationReport.failed("calculator result is not finite",
                                           ErrorType.MALFORMED, retryable=False)
        return ValidationReport.passed()
