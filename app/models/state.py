"""Mutable run state shared by executor, recovery and reporter."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.plan import Plan
from app.models.report import (
    ExecutionEvent,
    Metric,
    ReportBody,
    Source,
    TaskSummary,
    ToolCallRecord,
)
from app.models.tool_result import SearchHit


@dataclass
class ExecutionState:
    plan: Plan
    search_hits: dict[int, list[SearchHit]] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)
    task_summaries: dict[int, TaskSummary] = field(default_factory=dict)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    events: list[ExecutionEvent] = field(default_factory=list)
    report_body: ReportBody | None = None

    # --- sources -----------------------------------------------------------
    def add_source(
        self, *, url: str, title: str, snippet: str, text: str, retrieval: str, origin_task: int
    ) -> Source:
        existing = next((s for s in self.sources if s.url == url), None)
        if existing:
            return existing
        src = Source(
            id=len(self.sources) + 1,
            url=url,
            title=title,
            snippet=snippet,
            text=text,
            retrieval=retrieval,  # type: ignore[arg-type]
            origin_task=origin_task,
        )
        self.sources.append(src)
        return src

    def source_ids(self) -> set[int]:
        return {s.id for s in self.sources}

    # --- events ------------------------------------------------------------
    def record_event(
        self, kind: str, message: str, task_id: int | None = None, tool: str | None = None
    ) -> None:
        self.events.append(
            ExecutionEvent(task_id=task_id, kind=kind, message=message, tool=tool)  # type: ignore[arg-type]
        )

    @property
    def failure_count(self) -> int:
        return sum(1 for e in self.events if e.kind == "failure")

    @property
    def recovery_count(self) -> int:
        return sum(1 for e in self.events if e.kind in ("recovery", "fallback", "replan"))
