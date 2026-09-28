"""LLM re-planning: when a search task fails after all tool-level recovery
(retry + fallbacks), ask the LLM - with the failure as context - for a different
way to get the same information. The proposal is validated before it is used.

This is self-correction at the reasoning level, on top of the deterministic
tool-level recovery in recovery.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLMClient, LLMError, extract_json
from app.models.plan import Objective, Task

REPLAN_SYSTEM = """You are the re-planning module of a competitive-intelligence agent.
A web_search task failed even after retries and fallbacks. Propose ONE different search
query that is likely to return useful results for the same purpose (e.g. broader wording,
different angle, the company's product or market name). Do not repeat a failed query.
Return ONLY JSON: {"query": str or null, "reason": str}. Use null if there is no sensible
alternative."""


class ReplanProposal(BaseModel):
    query: str | None = Field(default=None, max_length=300)
    reason: str = Field(default="", max_length=400)


class LLMReplanner:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def alternative_query(
        self, objective: Objective, task: Task, failed_queries: list[str], errors: list[str]
    ) -> tuple[str | None, str]:
        """Return (new_query or None, reason). Never raises."""
        prompt = (
            f"Goal: {objective.raw_goal}\n"
            f"Target(s): {', '.join(objective.target_entities)} | market: {objective.market}\n"
            f"Failed task: {task.description}\n"
            f"Queries already tried: {failed_queries}\n"
            f"Errors: {errors[-3:]}"
        )
        try:
            proposal = ReplanProposal.model_validate(
                extract_json(self.llm.complete(REPLAN_SYSTEM, prompt, max_tokens=300)))
        except (LLMError, ValidationError, TypeError) as e:
            return None, f"re-planner unavailable ({type(e).__name__})"
        query = (proposal.query or "").strip()
        tried = {q.strip().lower() for q in failed_queries}
        if len(query) < 3:
            return None, proposal.reason or "LLM proposed no alternative"
        if query.lower() in tried:
            return None, "LLM repeated a query that already failed"
        return query, proposal.reason
