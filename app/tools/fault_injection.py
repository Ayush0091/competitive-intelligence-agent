"""Deliberate failure injection for demos and tests.

Wraps any Tool and corrupts its first N calls in a chosen way. The agent is
NOT told a fault was injected: detection must come from the validator.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.models.tool_result import ErrorType, ToolResult
from app.tools.base import Tool


class FailureMode(str, Enum):
    MALFORMED = "malformed"      # success=True but payload has the wrong shape
    EMPTY = "empty"              # success=True but zero results
    TIMEOUT = "timeout"          # simulated timeout error
    HTTP_ERROR = "http_error"    # simulated HTTP 503
    BAD_JSON = "bad_json"        # simulated JSON decode failure
    CRASH = "crash"              # tool raises an exception


class FaultInjectingTool(Tool):
    def __init__(self, inner: Tool, mode: FailureMode, fail_times: int = 1) -> None:
        self.inner = inner
        self.name = inner.name
        self.mode = mode
        self.remaining = fail_times
        self.injected = 0

    def describe(self) -> str:
        return self.inner.describe()

    def _run(self, **kwargs: Any) -> ToolResult:
        if self.remaining <= 0:
            return self.inner.run(**kwargs)
        self.remaining -= 1
        self.injected += 1
        return self._fault()

    def _fault(self) -> ToolResult:
        n = self.name
        if self.mode is FailureMode.MALFORMED:
            return ToolResult(tool=n, success=True, data={"unexpected": "invalid response"})
        if self.mode is FailureMode.EMPTY:
            return ToolResult(tool=n, success=True, data={"results": []})
        if self.mode is FailureMode.TIMEOUT:
            return ToolResult.fail(n, ErrorType.TIMEOUT, "request timed out (ReadTimeout)")
        if self.mode is FailureMode.HTTP_ERROR:
            return ToolResult.fail(n, ErrorType.HTTP_ERROR, "HTTP 503 Service Unavailable")
        if self.mode is FailureMode.BAD_JSON:
            return ToolResult.fail(n, ErrorType.MALFORMED,
                                   "malformed JSON response (Expecting value: line 1 column 1)")
        raise RuntimeError("injected tool crash")


def parse_injection(spec: str) -> tuple[str, FailureMode, int]:
    """Parse 'tool:mode[:times]', e.g. 'web_search:malformed' or 'url_fetcher:timeout:2'."""
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"bad --inject-failure spec '{spec}' (expected tool:mode[:times])")
    tool, mode = parts[0].strip(), parts[1].strip().lower()
    try:
        fm = FailureMode(mode)
    except ValueError as e:
        valid = ", ".join(m.value for m in FailureMode)
        raise ValueError(f"unknown failure mode '{mode}' (valid: {valid})") from e
    times = int(parts[2]) if len(parts) == 3 else 1
    if times < 1:
        raise ValueError("times must be >= 1")
    return tool, fm, times
