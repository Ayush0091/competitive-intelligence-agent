"""Failure recovery: validate -> retry (backoff) -> ordered fallbacks -> give up.

Every attempt is logged, recorded as a ToolCallRecord, and every failure /
recovery is recorded as an ExecutionEvent so it shows up in the final report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from app.models.report import ToolCallRecord
from app.models.state import ExecutionState
from app.models.tool_result import ToolResult, ValidationReport
from app.tools.base import Tool
from app.tracing import Tracer
from app.validator import ResultValidator

Strategy = Literal["first_try", "retry", "fallback", "gave_up"]


@dataclass(frozen=True)
class RecoveryPolicy:
    max_retries: int = 1
    backoff_s: float = 0.5


@dataclass(frozen=True)
class Fallback:
    label: str
    tool: Tool
    kwargs: dict[str, Any]


@dataclass
class RecoveryOutcome:
    ok: bool
    strategy: Strategy
    result: ToolResult | None = None
    validation: ValidationReport | None = None
    attempts: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def recovered(self) -> bool:
        return self.ok and self.strategy in ("retry", "fallback")


class RecoveryManager:
    def __init__(
        self, policy: RecoveryPolicy, validator: ResultValidator, tracer: Tracer,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy, self.validator, self.tracer, self._sleep = policy, validator, tracer, sleep

    def execute(
        self,
        *,
        state: ExecutionState,
        task_id: int | None,
        tool: Tool,
        kwargs: dict[str, Any],
        input_summary: str,
        fallbacks: list[Fallback] | None = None,
    ) -> RecoveryOutcome:
        errors: list[str] = []
        attempts = 0
        max_attempts = 1 + self.policy.max_retries

        # 1) primary attempt + retries
        for attempt in range(1, max_attempts + 1):
            attempts += 1
            role = "primary" if attempt == 1 else "retry"
            result, report = self._attempt(state, task_id, tool, kwargs, input_summary, attempt, role)
            if report.valid:
                if attempt > 1:
                    msg = f"Recovered via retry (attempt {attempt}/{max_attempts})"
                    self.tracer.log("RECOVERY", msg, task_id=task_id, tool=tool.name)
                    state.record_event("recovery", msg, task_id, tool.name)
                return RecoveryOutcome(True, "first_try" if attempt == 1 else "retry",
                                       result, report, attempts, errors)
            errors.append(report.issues[0] if report.issues else "unknown validation failure")
            if not report.retryable:
                self.tracer.log("RECOVERY", "Error is not retryable; skipping retries",
                                task_id=task_id, tool=tool.name)
                break
            if attempt < max_attempts:
                delay = self.policy.backoff_s * attempt
                why = "Validation failed" if result.success else "Tool call failed"
                self.tracer.log("RECOVERY", f"{why}. Retry attempt {attempt}/"
                                f"{self.policy.max_retries} in {delay:.1f}s...",
                                task_id=task_id, tool=tool.name)
                self._sleep(delay)

        # 2) ordered fallbacks
        for fb in fallbacks or []:
            attempts += 1
            self.tracer.log("RECOVERY", f"Switching to fallback: {fb.label}",
                            task_id=task_id, tool=fb.tool.name)
            summary = _summarize(fb.kwargs)
            result, report = self._attempt(state, task_id, fb.tool, fb.kwargs, summary,
                                           attempts, "fallback")
            if report.valid:
                msg = f"Recovered via fallback: {fb.label}"
                self.tracer.log("RECOVERY", msg, task_id=task_id, tool=fb.tool.name)
                state.record_event("fallback", msg, task_id, fb.tool.name)
                return RecoveryOutcome(True, "fallback", result, report, attempts, errors)
            errors.append(report.issues[0] if report.issues else "unknown validation failure")

        # 3) graceful failure
        msg = f"Giving up after {attempts} attempt(s): {errors[-1] if errors else 'unknown'}"
        self.tracer.log("RECOVERY", msg, task_id=task_id, tool=tool.name)
        state.record_event("gave_up", msg, task_id, tool.name)
        return RecoveryOutcome(False, "gave_up", None, None, attempts, errors)

    def _attempt(
        self, state: ExecutionState, task_id: int | None, tool: Tool, kwargs: dict[str, Any],
        input_summary: str, attempt: int, role: str,
    ) -> tuple[ToolResult, ValidationReport]:
        self.tracer.log("TOOL", f"{tool.describe()} {input_summary} (attempt {attempt})",
                        task_id=task_id, tool=tool.name, attempt=attempt, role=role)
        result = tool.run(**kwargs)
        report = self.validator.validate(result)
        err = None if report.valid else (report.issues[0] if report.issues else "invalid")
        state.tool_calls.append(ToolCallRecord(
            task_id=task_id, tool=tool.name, input_summary=input_summary[:160], attempt=attempt,
            success=report.valid, duration_ms=result.duration_ms, error=err, role=role,  # type: ignore[arg-type]
        ))
        if report.valid:
            extra = f" (warnings: {len(report.warnings)})" if report.warnings else ""
            self.tracer.log("VALIDATION", f"passed in {result.duration_ms:.0f} ms{extra}",
                            task_id=task_id, tool=tool.name, duration_ms=result.duration_ms)
        else:
            etype = report.error_type.value if report.error_type else "unknown"
            self.tracer.log("ERROR", f"{err} [{etype}]", task_id=task_id, tool=tool.name,
                            duration_ms=result.duration_ms, error_type=etype)
            state.record_event("failure", f"{tool.name}: {err} [{etype}]", task_id, tool.name)
        return result, report


def _summarize(kwargs: dict[str, Any]) -> str:
    parts = []
    for k, v in kwargs.items():
        s = str(v)
        parts.append(f'{k}="{s[:90]}{"..." if len(s) > 90 else ""}"')
    return " ".join(parts)


summarize_input = _summarize
