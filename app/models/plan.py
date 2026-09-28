"""Structured objective and execution plan produced by the planner."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ToolName = Literal["web_search", "url_fetcher", "calculator", "synthesize"]
EXTERNAL_TOOLS: tuple[str, ...] = ("web_search", "url_fetcher", "calculator")


class AnalysisType(str, Enum):
    LANDSCAPE = "landscape"
    COMPARISON = "comparison"
    DEVELOPMENTS = "developments"


class Objective(BaseModel):
    """The user's goal converted into a structured objective."""

    raw_goal: str
    target_entities: list[str] = Field(min_length=1, max_length=5)
    analysis_type: AnalysisType = AnalysisType.LANDSCAPE
    market: str | None = None

    @field_validator("target_entities")
    @classmethod
    def _clean_entities(cls, v: list[str]) -> list[str]:
        cleaned = [e.strip() for e in v if e and e.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty target entity is required")
        return cleaned

    @property
    def primary(self) -> str:
        return self.target_entities[0]


class Task(BaseModel):
    id: int = Field(ge=1)
    description: str = Field(min_length=3, max_length=200)
    tool: ToolName
    query: str | None = Field(default=None, max_length=300)
    depends_on: list[int] = Field(default_factory=list)
    max_items: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def _check_args(self) -> "Task":
        if self.tool == "web_search" and not (self.query and self.query.strip()):
            raise ValueError(f"task {self.id}: web_search requires a non-empty 'query'")
        if self.tool in ("url_fetcher", "calculator", "synthesize") and not self.depends_on:
            raise ValueError(f"task {self.id}: {self.tool} must depend on earlier tasks")
        return self


class Plan(BaseModel):
    goal: str
    objective: Objective
    tasks: list[Task] = Field(min_length=2, max_length=12)
    planner: Literal["llm", "template"] = "template"

    @model_validator(mode="after")
    def _check_structure(self) -> "Plan":
        ids = [t.id for t in self.tasks]
        if ids != list(range(1, len(ids) + 1)):
            raise ValueError(f"task ids must be sequential starting at 1, got {ids}")
        by_id = {t.id: t for t in self.tasks}
        for t in self.tasks:
            for dep in t.depends_on:
                if dep >= t.id or dep not in by_id:
                    raise ValueError(f"task {t.id} depends on invalid/later task {dep}")
            if t.tool == "url_fetcher" and not any(
                by_id[d].tool == "web_search" for d in t.depends_on
            ):
                raise ValueError(f"task {t.id}: url_fetcher must depend on a web_search task")
        if not any(t.tool == "web_search" for t in self.tasks):
            raise ValueError("plan must contain at least one web_search task")
        synth = [t for t in self.tasks if t.tool == "synthesize"]
        if len(synth) != 1 or self.tasks[-1].tool != "synthesize":
            raise ValueError("plan must end with exactly one 'synthesize' task")
        return self

    def tools_used(self) -> list[str]:
        seen: list[str] = []
        for t in self.tasks:
            if t.tool in EXTERNAL_TOOLS and t.tool not in seen:
                seen.append(t.tool)
        return seen
