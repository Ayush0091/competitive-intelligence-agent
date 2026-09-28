"""Uniform result envelope returned by every tool, plus validation reports."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ErrorType(str, Enum):
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    NETWORK = "network_error"
    INVALID_INPUT = "invalid_input"
    MALFORMED = "malformed_response"
    EMPTY = "empty_result"
    UNSUPPORTED_CONTENT = "unsupported_content"
    CONFIG = "config_error"
    UNKNOWN = "unknown"


class ToolError(BaseModel):
    type: ErrorType
    message: str
    retryable: bool = True


class ToolResult(BaseModel):
    """What every tool returns. Tools never raise; they report errors here."""

    tool: str
    success: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(cls, tool: str, data: dict[str, Any], **metadata: Any) -> "ToolResult":
        return cls(tool=tool, success=True, data=data, metadata=metadata)

    @classmethod
    def fail(
        cls,
        tool: str,
        error_type: ErrorType,
        message: str,
        *,
        retryable: bool = True,
        **metadata: Any,
    ) -> "ToolResult":
        return cls(
            tool=tool,
            success=False,
            error=ToolError(type=error_type, message=message, retryable=retryable),
            metadata=metadata,
        )


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str = ""


class ValidationReport(BaseModel):
    """Outcome of checking a ToolResult. `valid` decides whether the result is used."""

    valid: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_type: ErrorType | None = None
    retryable: bool = True

    @classmethod
    def passed(cls, warnings: list[str] | None = None) -> "ValidationReport":
        return cls(valid=True, warnings=warnings or [])

    @classmethod
    def failed(
        cls, issue: str, error_type: ErrorType, retryable: bool = True
    ) -> "ValidationReport":
        return cls(valid=False, issues=[issue], error_type=error_type, retryable=retryable)
