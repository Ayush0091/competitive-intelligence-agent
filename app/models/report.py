"""Report, source and execution-record models (the machine-readable output)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FindingKind = Literal["fact", "inference"]
TaskStatus = Literal["completed", "completed_with_recovery", "failed", "skipped"]


class Source(BaseModel):
    id: int
    url: str
    title: str
    snippet: str = ""
    text: str = Field(default="", exclude=True)  # kept in memory, not dumped to JSON
    retrieval: Literal["full_page", "snippet_only"] = "full_page"
    origin_task: int

    @property
    def content(self) -> str:
        return self.text or self.snippet


class Metric(BaseModel):
    label: str
    expression: str
    value: float | None = None
    unit: str = ""
    source_ids: list[int] = Field(default_factory=list)
    status: Literal["ok", "failed"] = "ok"
    error: str | None = None


class Finding(BaseModel):
    text: str
    source_ids: list[int] = Field(default_factory=list)
    kind: FindingKind = "fact"


class CompetitorEntry(BaseModel):
    name: str
    summary: str = ""
    source_ids: list[int] = Field(default_factory=list)
    kind: FindingKind = "fact"


class ReportBody(BaseModel):
    target_company: str
    executive_summary: str
    competitors: list[CompetitorEntry] = Field(default_factory=list)
    recent_developments: list[Finding] = Field(default_factory=list)
    market_signals: list[Finding] = Field(default_factory=list)
    risks: list[Finding] = Field(default_factory=list)
    synthesis_method: str = "extractive"


class ToolCallRecord(BaseModel):
    task_id: int | None
    tool: str
    input_summary: str
    attempt: int
    success: bool
    duration_ms: float
    error: str | None = None
    role: Literal["primary", "retry", "fallback"] = "primary"


class ExecutionEvent(BaseModel):
    task_id: int | None
    kind: Literal["failure", "recovery", "fallback", "replan", "gave_up", "info"]
    message: str
    tool: str | None = None


class TaskSummary(BaseModel):
    id: int
    description: str
    tool: str
    status: TaskStatus
    note: str = ""


class RunReport(BaseModel):
    goal: str
    status: Literal["completed", "completed_with_warnings", "failed"]
    data_mode: Literal["live", "offline_synthetic"] = "live"
    planner: str
    llm: str
    tasks_total: int
    tasks_completed: int
    tasks_failed: int
    tools_used: list[str]
    failures: int
    recoveries: int
    sources_analyzed: int
    report: ReportBody
    metrics: list[Metric] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    tasks: list[TaskSummary] = Field(default_factory=list)
    events: list[ExecutionEvent] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    started_at: str
    duration_s: float
