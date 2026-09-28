"""Agent controller + dependency wiring.

Goal -> Planner -> (display plan) -> TaskExecutor[Router -> Tool -> Validator
-> Recovery] -> Synthesizer -> Reporter -> JSON + Markdown.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import httpx

from app.config import Settings
from app.executor import TaskExecutor
from app.llm import LLMClient, TimedLLM, build_llm
from app.metrics import LLMMetricExtractor, MetricExtractor, RegexMetricExtractor
from app.models.report import RunReport
from app.models.state import ExecutionState
from app.planner import LLMPlanner, Planner, PlanningError, TemplatePlanner, render_plan
from app.recovery import RecoveryManager, RecoveryPolicy
from app.replanner import LLMReplanner
from app.reporter import build_run_report, render_markdown
from app.synthesizer import ExtractiveSynthesizer, LLMSynthesizer, Synthesizer
from app.tools.calculator import CalculatorTool
from app.tools.fault_injection import FailureMode, FaultInjectingTool
from app.tools.router import ToolRouter
from app.tools.synthetic import SyntheticSearchProvider, synthetic_transport
from app.tools.url_fetcher import UrlFetcherTool
from app.tools.keyless_search import BingRssProvider, DuckDuckGoProvider
from app.tools.web_search import TavilyProvider, WebSearchTool, WikipediaProvider
from app.tracing import Tracer
from app.validator import ResultValidator

Injection = tuple[str, FailureMode, int]


@dataclass
class RunResult:
    report: RunReport
    markdown: str
    output_dir: Path | None = None
    files: dict[str, Path] = field(default_factory=dict)


class CompetitiveIntelligenceAgent:
    def __init__(
        self, *, planner: Planner, executor: TaskExecutor, tracer: Tracer, settings: Settings,
        llm_name: str, data_mode: str, planner_note: str = "", injections: list[Injection] | None = None,
    ) -> None:
        self.planner, self.executor, self.tracer = planner, executor, tracer
        self.settings, self.llm_name, self.data_mode = settings, llm_name, data_mode
        self.planner_note, self.injections = planner_note, injections or []

    def run(self, goal: str, output_dir: Path | None = None) -> RunResult:
        started, t0 = datetime.now(), time.perf_counter()
        self.tracer.log("AGENT", f'Goal received: "{goal}"')
        self.tracer.log("AGENT", f"mode={self.data_mode} | llm={self.llm_name} | "
                        f"search={self.executor.router.get('web_search').describe()}")
        for tool, mode, times in self.injections:
            self.tracer.log("FAULT", f"Deliberate failure armed: {tool} -> '{mode.value}' "
                            f"for the next {times} call(s) (validator is not told)")

        try:
            plan = self.planner.create_plan(goal)
        except PlanningError as e:
            self.tracer.log("ERROR", f"Could not interpret goal: {e}")
            raise
        note = self.planner_note
        if plan.planner == "template" and isinstance(self.planner, LLMPlanner):
            note = "LLM plan invalid -> deterministic template fallback"
        self.tracer.raw("\n" + render_plan(plan, max_retries=self.settings.max_retries,
                                           planner_note=note,
                                           replanning=self.executor.replanner is not None) + "\n")

        state = ExecutionState(plan=plan)
        if hasattr(self.planner, "copy_events_to"):
            self.planner.copy_events_to(state)  # type: ignore[attr-defined]
        self.executor.run(plan, state)

        report = build_run_report(state, started_at=started, duration_s=time.perf_counter() - t0,
                                  llm_name=self.llm_name, data_mode=self.data_mode)
        markdown = render_markdown(report)
        self.tracer.log("RESULT", f"status={report.status} | tasks {report.tasks_completed}/"
                        f"{report.tasks_total} | tool calls={len(report.tool_calls)} | "
                        f"failures={report.failures} | recoveries={report.recoveries} | "
                        f"sources={report.sources_analyzed}")
        result = RunResult(report=report, markdown=markdown, output_dir=output_dir)
        if output_dir:
            result.files = save_outputs(report, markdown, output_dir)
            self.tracer.log("RESULT", f"Saved {', '.join(str(p) for p in result.files.values())}")
        return result


def save_outputs(report: RunReport, markdown: str, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = output_dir / "report.json", output_dir / "report.md"
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def run_dir_for(goal: str, base: Path) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")[:40] or "run"
    return base / f"{datetime.now():%Y%m%d-%H%M%S}_{slug}"


def _live_search_tools(settings: Settings, timeout: float) -> list[WebSearchTool]:
    """Primary search tool followed by its ordered fallbacks.

    Default (no keys): DuckDuckGo -> Bing web RSS -> Bing news RSS, none of which need
    an account. Tavily is used first when TAVILY_API_KEY is set. Wikipedia is added
    only when AGENT_CONTACT is set, because Wikimedia rejects anonymous agents (403).
    """
    ddg = WebSearchTool(DuckDuckGoProvider(timeout=timeout))
    bing_web = WebSearchTool(BingRssProvider("web", timeout=timeout))
    bing_news = WebSearchTool(BingRssProvider("news", timeout=timeout))
    wiki = ([WebSearchTool(WikipediaProvider(timeout=timeout, contact=settings.agent_contact))]
            if settings.agent_contact else [])
    choice = settings.search_provider
    if settings.tavily_api_key and choice in ("auto", "tavily"):
        return [WebSearchTool(TavilyProvider(settings.tavily_api_key, timeout=timeout)),
                ddg, bing_news]
    if choice == "wikipedia" and wiki:
        return wiki + [ddg, bing_web]
    if choice == "bing":
        return [bing_web, bing_news, ddg] + wiki
    return [ddg, bing_web, bing_news] + wiki


def build_agent(
    settings: Settings, tracer: Tracer, *, offline: bool = False, use_llm: bool = True,
    injections: list[Injection] | None = None, llm: LLMClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> CompetitiveIntelligenceAgent:
    """Wire all components. Every dependency is injectable for tests."""
    injections = injections or []
    validator = ResultValidator()
    llm_note = ""
    # Offline mode means "no internet": a local Ollama model still works there.
    if llm is None and use_llm and (not offline or settings.llm_provider == "ollama"):
        llm = build_llm(settings)
        check = getattr(llm, "check", None)
        if llm is not None and callable(check):
            ok, msg = check()
            tracer.log("AGENT", f"LLM health check: {msg}")
            if not ok:  # don't wait on timeouts for a model that is not there
                tracer.log("AGENT", "LLM unavailable -> using deterministic planner/synthesizer")
                llm, llm_note = None, f"LLM unavailable ({msg})"
    if llm is not None and not isinstance(llm, TimedLLM):
        llm = TimedLLM(llm, tracer.log)
    llm_name = llm.name if llm else "none"

    router = ToolRouter()
    if offline:
        data_mode = "offline_synthetic"
        router.register(WebSearchTool(SyntheticSearchProvider(name="synthetic")),
                        WebSearchTool(SyntheticSearchProvider(name="synthetic-backup")))
        fetch_client = httpx.Client(transport=synthetic_transport(), follow_redirects=True)
        router.register(UrlFetcherTool(client=fetch_client, max_chars=settings.max_page_chars))
    else:
        data_mode = "live"
        timeout = settings.http_timeout_s
        router.register(*_live_search_tools(settings, timeout))
        router.register(UrlFetcherTool(timeout=timeout, max_chars=settings.max_page_chars))
    router.register(CalculatorTool())

    for tool_name, mode, times in injections:
        router.wrap(tool_name, FaultInjectingTool, mode, times)

    recovery = RecoveryManager(RecoveryPolicy(settings.max_retries, settings.retry_backoff_s),
                               validator, tracer, sleep=sleep)
    template = TemplatePlanner()
    planner: Planner
    metric_extractor: MetricExtractor
    synthesizer: Synthesizer
    replanner = None
    if llm:
        replanner = LLMReplanner(llm)
        planner = LLMPlanner(llm, tracer, template, settings.max_retries)
        metric_extractor = LLMMetricExtractor(llm)
        synthesizer = LLMSynthesizer(llm, validator, ExtractiveSynthesizer(), settings.max_retries)
        note = f"LLM {llm.name}"
    else:
        planner, metric_extractor, synthesizer = template, RegexMetricExtractor(), ExtractiveSynthesizer()
        note = llm_note or "no LLM configured -> deterministic rule-based planner"

    executor = TaskExecutor(router=router, validator=validator, recovery=recovery, tracer=tracer,
                            metric_extractor=metric_extractor, synthesizer=synthesizer,
                            max_sources=settings.max_sources, replanner=replanner)
    return CompetitiveIntelligenceAgent(planner=planner, executor=executor, tracer=tracer,
                                        settings=settings, llm_name=llm_name, data_mode=data_mode,
                                        planner_note=note, injections=injections)
