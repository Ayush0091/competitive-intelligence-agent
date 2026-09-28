"""Sequential task executor: routes each planned task to its handler/tool,
runs it through the RecoveryManager, and records results in ExecutionState."""

from __future__ import annotations

from typing import Callable

from app.metrics import MetricExtractor
from app.models.plan import Plan, Task
from app.models.report import Metric, TaskSummary
from app.models.state import ExecutionState
from app.models.tool_result import SearchHit
from app.recovery import Fallback, RecoveryManager, RecoveryOutcome, summarize_input
from app.replanner import LLMReplanner
from app.synthesizer import Synthesizer
from app.text_utils import detect_companies
from app.tools.router import ToolRouter
from app.tracing import Tracer
from app.validator import ResultValidator, is_relevant, relevance_terms

MIN_SNIPPET_CHARS = 40


class TaskExecutor:
    def __init__(
        self, *, router: ToolRouter, validator: ResultValidator, recovery: RecoveryManager,
        tracer: Tracer, metric_extractor: MetricExtractor, synthesizer: Synthesizer,
        max_sources: int = 6, replanner: LLMReplanner | None = None,
    ) -> None:
        self.replanner = replanner
        self.router, self.validator, self.recovery = router, validator, recovery
        self.tracer, self.metric_extractor, self.synthesizer = tracer, metric_extractor, synthesizer
        self.max_sources = max_sources
        self._handlers: dict[str, Callable[[Task, ExecutionState], TaskSummary]] = {
            "web_search": self._run_search,
            "url_fetcher": self._run_fetch,
            "calculator": self._run_calculator,
            "synthesize": self._run_synthesis,
        }

    def run(self, plan: Plan, state: ExecutionState | None = None) -> ExecutionState:
        state = state or ExecutionState(plan=plan)
        self.tracer.log("PLAN", f"{len(plan.tasks)} tasks generated; executing sequentially")
        for task in plan.tasks:
            self.tracer.log(f"TASK {task.id}", f"{task.description}", task_id=task.id)
            summary = self._handlers[task.tool](task, state)
            state.task_summaries[task.id] = summary
            note = f" - {summary.note}" if summary.note else ""
            self.tracer.log(f"TASK {task.id}", f"{summary.status.upper()}{note}",
                            task_id=task.id, status=summary.status)
        return state

    # ------------------------------------------------------------------ search
    def _run_search(self, task: Task, state: ExecutionState) -> TaskSummary:
        tool = self.router.get("web_search")
        query = task.query or ""
        fallbacks = [Fallback(f"secondary search provider ({fb.describe()})", fb, {"query": query})
                     for fb in self.router.get_fallbacks("web_search")]
        simple = _simplify_query(query, state.plan.objective.target_entities)
        if simple and simple != query:
            fallbacks.append(Fallback(f'simplified query "{simple}"', tool, {"query": simple}))
        outcome = self.recovery.execute(
            state=state, task_id=task.id, tool=tool, kwargs={"query": query},
            input_summary=summarize_input({"query": query}), fallbacks=fallbacks)
        replanned = False
        if (not outcome.ok or outcome.result is None) and self.replanner:
            tried = [query] + [fb.kwargs["query"] for fb in fallbacks]
            outcome, replanned = self._replan_search(task, state, tool, tried, outcome.errors)
        if not outcome.ok or outcome.result is None:
            state.search_hits[task.id] = []
            return self._summary(task, "failed", "search failed after retries/fallbacks/re-plan")
        hits = self.validator.search_hits(outcome.result)[: task.max_items]
        state.search_hits[task.id] = hits
        provider = (outcome.result.data or {}).get("provider", "?")
        self.tracer.log("RESULT", f"{len(hits)} valid results (provider={provider})",
                        task_id=task.id, results=len(hits))
        for h in hits:
            self.tracer.log("RESULT", f"  - {h.title[:80]} | {h.url}", task_id=task.id)
        status = "completed_with_recovery" if outcome.recovered or replanned else "completed"
        how = "LLM re-plan" if replanned else outcome.strategy
        return self._summary(task, status, f"{len(hits)} results via {how}")

    def _replan_search(self, task: Task, state: ExecutionState, tool, tried: list[str],
                       errors: list[str]):
        """Reasoning-level recovery: ask the LLM for a different query, then run it."""
        assert self.replanner is not None
        self.tracer.log("REPLAN", "Tool-level recovery exhausted; asking the LLM for an "
                        "alternative approach", task_id=task.id)
        new_query, reason = self.replanner.alternative_query(
            state.plan.objective, task, tried, errors)
        if not new_query:
            self.tracer.log("REPLAN", f"No alternative: {reason}", task_id=task.id)
            state.record_event("info", f"Re-plan declined: {reason}", task.id, "planner")
            return RecoveryOutcome(False, "gave_up", errors=errors), False
        self.tracer.log("REPLAN", f'New query "{new_query}" - {reason}', task_id=task.id)
        outcome = self.recovery.execute(
            state=state, task_id=task.id, tool=tool, kwargs={"query": new_query},
            input_summary=summarize_input({"query": new_query}))
        if outcome.ok:
            state.record_event("replan", f'Recovered via LLM re-plan: new query "{new_query}"',
                               task.id, "planner")
        return outcome, outcome.ok

    # ------------------------------------------------------------------- fetch
    def _run_fetch(self, task: Task, state: ExecutionState) -> TaskSummary:
        hits = self._candidate_hits(task, state)
        if not hits:
            return self._summary(task, "failed", "no search results available to fetch")
        tool = self.router.get("url_fetcher")
        full = snippet = skipped = 0
        for hit in hits:
            outcome = self.recovery.execute(
                state=state, task_id=task.id, tool=tool, kwargs={"url": hit.url},
                input_summary=summarize_input({"url": hit.url}))
            if outcome.ok and outcome.result and outcome.result.data:
                d = outcome.result.data
                src = state.add_source(url=hit.url, title=d.get("title") or hit.title,
                                       snippet=hit.snippet, text=d["text"],
                                       retrieval="full_page", origin_task=task.id)
                full += 1
                self.tracer.log("RESULT", f"S{src.id}: {d.get('chars', 0)} chars extracted"
                                f"{' (truncated)' if d.get('truncated') else ''}", task_id=task.id)
            elif len(hit.snippet.strip()) >= MIN_SNIPPET_CHARS:
                src = state.add_source(url=hit.url, title=hit.title, snippet=hit.snippet, text="",
                                       retrieval="snippet_only", origin_task=task.id)
                snippet += 1
                msg = f"Degraded gracefully: using search snippet for S{src.id} instead of full page"
                self.tracer.log("RECOVERY", msg, task_id=task.id)
                state.record_event("fallback", msg, task.id, "url_fetcher")
            else:
                skipped += 1
                self.tracer.log("RECOVERY", f"Skipping {hit.url}: no usable content", task_id=task.id)
        note = f"{full} full pages, {snippet} snippet fallbacks, {skipped} skipped"
        if full + snippet == 0:
            return self._summary(task, "failed", note)
        return self._summary(task, "completed_with_recovery" if snippet or skipped else "completed", note)

    def _candidate_hits(self, task: Task, state: ExecutionState) -> list[SearchHit]:
        """Relevant hits only, round-robin across dependent searches, de-duplicated."""
        obj = state.plan.objective
        terms = relevance_terms(obj.target_entities, obj.market)
        raw = [state.search_hits.get(d, []) for d in task.depends_on]
        lists = [[h for h in lst if is_relevant(h, terms)] for lst in raw]
        dropped = sum(len(a) - len(b) for a, b in zip(raw, lists))
        if dropped:
            self.tracer.log("VALIDATION", f"Skipped {dropped} off-topic search result(s) that "
                            f"mention none of {sorted(terms)}", task_id=task.id)
            state.record_event("info", f"filtered {dropped} off-topic search results", task.id,
                               "url_fetcher")
        if not any(lists):  # never starve the run: fall back to unfiltered results
            lists = raw
        limit = min(task.max_items, self.max_sources)
        seen = {s.url for s in state.sources}
        out: list[SearchHit] = []
        for rank in range(max((len(x) for x in lists), default=0)):
            for lst in lists:
                if rank < len(lst) and lst[rank].url not in seen:
                    seen.add(lst[rank].url)
                    out.append(lst[rank])
                if len(out) >= limit:
                    return out
        return out

    # -------------------------------------------------------------- calculator
    def _run_calculator(self, task: Task, state: ExecutionState) -> TaskSummary:
        if not state.sources:
            return self._summary(task, "skipped", "no sources to extract figures from")
        entities = self._entities(state)
        requests = self.metric_extractor.extract(state.plan.objective, state.sources, entities)
        for note in getattr(self.metric_extractor, "rejected", []):
            self.tracer.log("VALIDATION", note, task_id=task.id)
            state.record_event("info", note, task.id, "calculator")
        if not requests:
            notes = getattr(self.metric_extractor, "rejected", [])
            note = (f"{notes[-1]} (nothing computed)" if notes
                    else "no comparable numeric figures found in sources (nothing computed)")
            return self._summary(task, "skipped", note)
        tool = self.router.get("calculator")
        ok = 0
        for req in requests:
            outcome = self.recovery.execute(
                state=state, task_id=task.id, tool=tool, kwargs={"expression": req.expression},
                input_summary=summarize_input({"expression": req.expression}))
            if outcome.ok and outcome.result and outcome.result.data:
                value = float(outcome.result.data["result"])
                state.metrics.append(Metric(label=req.label, expression=req.expression,
                                            value=value, unit=req.unit, source_ids=req.source_ids))
                self.tracer.log("RESULT", f"{req.label} = {value:.2f}{req.unit}", task_id=task.id)
                ok += 1
            else:
                state.metrics.append(Metric(label=req.label, expression=req.expression,
                                            unit=req.unit, source_ids=req.source_ids,
                                            status="failed", error="; ".join(outcome.errors)))
        status = "completed" if ok == len(requests) else ("failed" if ok == 0 else "completed_with_recovery")
        return self._summary(task, status, f"{ok}/{len(requests)} metrics computed")

    # --------------------------------------------------------------- synthesis
    def _run_synthesis(self, task: Task, state: ExecutionState) -> TaskSummary:
        if not state.sources:
            return self._summary(task, "failed", "no validated sources; cannot synthesize")
        competitors: list[str] = []
        if self.synthesizer.name == "extractive":  # the LLM identifies competitors itself
            competitors = detect_companies(state.sources, state.plan.objective.target_entities)
            self.tracer.log("RESULT", "heuristic competitor candidates: "
                            f"{', '.join(competitors) or 'none'}", task_id=task.id)
        state.report_body = self.synthesizer.synthesize(
            state.plan.objective, state.sources, state.metrics, competitors)
        for note in self.synthesizer.notes:
            kind = "fallback" if "Fell back" in note else "info"
            self.tracer.log("VALIDATION", note, task_id=task.id)
            state.record_event(kind, note, task.id, "synthesize")
        body = state.report_body
        return self._summary(task, "completed",
                             f"{self.synthesizer.name}: {len(body.competitors)} competitors, "
                             f"{len(body.recent_developments)} developments, "
                             f"{len(body.market_signals)} signals, {len(body.risks)} risks")

    # ----------------------------------------------------------------- helpers
    def _entities(self, state: ExecutionState) -> list[str]:
        targets = state.plan.objective.target_entities
        return targets + [c for c in detect_companies(state.sources, targets) if c not in targets]

    @staticmethod
    def _summary(task: Task, status: str, note: str) -> TaskSummary:
        return TaskSummary(id=task.id, description=task.description, tool=task.tool,
                           status=status, note=note)  # type: ignore[arg-type]


def _simplify_query(query: str, entities: list[str]) -> str:
    """Fallback query: primary entity + at most two informative words from the original."""
    if not entities:
        return ""
    entity = entities[0]
    rest = [w for w in query.replace(entity, "").split()
            if len(w) > 3 and w.lower() not in {"recent", "developments", "latest", "market"}]
    return " ".join([entity] + rest[:2]).strip()
