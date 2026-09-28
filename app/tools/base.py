"""Common tool interface. Tools never raise: every outcome is a ToolResult."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.models.tool_result import ErrorType, ToolResult

USER_AGENT = "CompetitiveIntelligenceAgent/1.0 (research prototype)"


def user_agent(contact: str | None = None) -> str:
    """User-Agent with optional operator contact (Wikimedia requires an email or URL)."""
    return f"CompetitiveIntelligenceAgent/1.0 (+{contact})" if contact else USER_AGENT


class Tool(ABC):
    name: str = "tool"

    def run(self, **kwargs: Any) -> ToolResult:
        """Timed, exception-safe wrapper around `_run`."""
        start = time.perf_counter()
        try:
            result = self._run(**kwargs)
        except Exception as e:  # last-resort guard: a bug must not crash the agent
            result = ToolResult.fail(self.name, ErrorType.UNKNOWN, f"{type(e).__name__}: {e}")
        result.duration_ms = round((time.perf_counter() - start) * 1000, 1)
        return result

    @abstractmethod
    def _run(self, **kwargs: Any) -> ToolResult: ...

    def describe(self) -> str:
        return self.name


def classify_http_error(exc: Exception) -> tuple[ErrorType, str, bool]:
    """Map an httpx/JSON exception to (error type, message, retryable)."""
    if isinstance(exc, httpx.TimeoutException):
        return ErrorType.TIMEOUT, f"request timed out ({type(exc).__name__})", True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        retryable = code == 429 or code >= 500
        return ErrorType.HTTP_ERROR, f"HTTP {code} {exc.response.reason_phrase}".strip(), retryable
    if isinstance(exc, httpx.RequestError):
        return ErrorType.NETWORK, f"network error ({type(exc).__name__})", True
    if isinstance(exc, ValueError):  # includes json.JSONDecodeError
        return ErrorType.MALFORMED, f"malformed JSON response ({exc})"[:200], True
    return ErrorType.UNKNOWN, f"{type(exc).__name__}: {exc}", False
