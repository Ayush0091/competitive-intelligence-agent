"""Build the machine-readable RunReport and render the Markdown report."""

from __future__ import annotations

from datetime import datetime

from app.models.report import Finding, ReportBody, RunReport
from app.models.state import ExecutionState


def build_run_report(
    state: ExecutionState, *, started_at: datetime, duration_s: float, llm_name: str,
    data_mode: str = "live",
) -> RunReport:
    plan = state.plan
    summaries = [state.task_summaries[t.id] for t in plan.tasks if t.id in state.task_summaries]
    done = sum(1 for s in summaries if s.status in ("completed", "completed_with_recovery"))
    failed = sum(1 for s in summaries if s.status == "failed")
    body = state.report_body or ReportBody(
        target_company=", ".join(plan.objective.target_entities),
        executive_summary="No report could be produced: no validated sources were obtained. "
                          "See the execution summary for the failures encountered.",
        synthesis_method="none")
    if state.report_body is None or not state.sources:
        status = "failed"
    elif failed == 0:
        status = "completed"  # skipped tasks (e.g. no numbers to compute) are not failures
    else:
        status = "completed_with_warnings"
    tools_used = sorted({c.tool for c in state.tool_calls})
    return RunReport(
        goal=plan.goal, status=status, data_mode=data_mode,  # type: ignore[arg-type]
        planner=plan.planner, llm=llm_name,
        tasks_total=len(plan.tasks), tasks_completed=done, tasks_failed=failed,
        tools_used=tools_used, failures=state.failure_count, recoveries=state.recovery_count,
        sources_analyzed=len(state.sources), report=body, metrics=state.metrics,
        sources=state.sources, tasks=summaries, events=state.events, tool_calls=state.tool_calls,
        started_at=started_at.isoformat(timespec="seconds"), duration_s=round(duration_s, 2),
    )


def _cite(ids: list[int]) -> str:
    return "".join(f"[S{i}]" for i in ids)


def _finding_line(f: Finding) -> str:
    if f.kind == "fact":
        return f"- {f.text} {_cite(f.source_ids)}".rstrip()
    support = f" (supported by {_cite(f.source_ids)})" if f.source_ids else ""
    return f"- *Analysis:* {f.text}{support}"


def _section(title: str, items: list[Finding], empty: str) -> list[str]:
    lines = [f"## {title}", ""]
    lines += [_finding_line(f) for f in items] if items else [f"_{empty}_"]
    return lines + [""]


def render_markdown(r: RunReport) -> str:
    b = r.report
    out: list[str] = ["# Competitive Landscape Report", ""]
    if r.data_mode == "offline_synthetic":
        out += ["> **OFFLINE SYNTHETIC MODE** - all companies, sources and figures below come from "
                "a fictional test corpus (`data/synthetic_corpus.json`). Not real information.", ""]
    out += [f"**Goal:** {r.goal}  ", f"**Status:** `{r.status}`  ",
            f"**Generated:** {r.started_at} | planner: `{r.planner}` | LLM: `{r.llm}` | "
            f"synthesis: {b.synthesis_method}", "",
            "> Legend: bullet points ending in `[S#]` are **sourced facts** (see Sources). "
            "Lines marked *Analysis* are **inference** by the agent.", ""]
    out += ["## Target Company", "", b.target_company, ""]
    out += ["## Executive Summary", "", f"*Analysis:* {b.executive_summary}", ""]

    out += ["## Major Competitors", ""]
    if b.competitors:
        for c in b.competitors:
            tag = _cite(c.source_ids) if c.kind == "fact" else "*(analysis)*"
            out.append(f"- **{c.name}** - {c.summary} {tag}".rstrip())
    else:
        out.append("_No competitors could be identified from the retrieved sources._")
    out.append("")

    out += _section("Recent Developments", b.recent_developments,
                    "No recent developments found in the retrieved sources.")
    out += _section("Competitive Signals", b.market_signals,
                    "No competitive signals found in the retrieved sources.")
    ok_metrics = [m for m in r.metrics if m.status == "ok"]
    if r.metrics:
        out += ["### Computed Metrics (calculator tool)", "",
                "| Metric | Value | Expression | Inputs from |", "|---|---|---|---|"]
        for m in r.metrics:
            val = f"{m.value:.2f}{m.unit}" if m.status == "ok" and m.value is not None else f"failed: {m.error}"
            out.append(f"| {m.label} | {val} | `{m.expression}` | {_cite(m.source_ids)} |")
        out += ["", "_Values are computed deterministically from figures stated in the cited "
                "sources; they inherit those sources' definitions and periods._", ""]
    elif not ok_metrics:
        calc = next((t for t in r.tasks if t.tool == "calculator"), None)
        reason = calc.note if calc and calc.note else "no comparable numeric figures were found"
        out += [f"_No metrics were computed: {reason}._", ""]
    out += _section("Risks / Challenges", b.risks, "No risks found in the retrieved sources.")

    out += ["## Sources", ""]
    if r.sources:
        for s in r.sources:
            kind = "full page" if s.retrieval == "full_page" else "search snippet only"
            out.append(f"- **[S{s.id}]** {s.title} - <{s.url}> ({kind})")
    else:
        out.append("_No sources were successfully retrieved._")
    out.append("")

    out += ["## Agent Execution Summary", "",
            f"- Tasks: {r.tasks_completed}/{r.tasks_total} completed, {r.tasks_failed} failed",
            f"- Tools used: {', '.join(r.tools_used) or 'none'}",
            f"- Tool calls: {len(r.tool_calls)} | failures detected: {r.failures} | "
            f"recoveries: {r.recoveries}",
            f"- Sources analyzed: {r.sources_analyzed} | duration: {r.duration_s}s", "",
            "| # | Task | Tool | Status | Note |", "|---|---|---|---|---|"]
    for t in r.tasks:
        out.append(f"| {t.id} | {t.description} | {t.tool} | {t.status} | {t.note} |")
    notable = [e for e in r.events if e.kind != "info"]
    if notable:
        out += ["", "**Failures and recoveries:**", ""]
        for e in notable:
            where = f"task {e.task_id}" if e.task_id else "planning"
            out.append(f"- `{e.kind}` ({where}, {e.tool or '-'}): {e.message}")
    out.append("")
    return "\n".join(out)
