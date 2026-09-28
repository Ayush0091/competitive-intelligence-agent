"""Validator + recovery tests. Failures are real: tools actually return bad data."""

from typing import Any

import pytest

from app.agent import build_agent
from app.models.tool_result import ErrorType, ToolResult
from app.recovery import Fallback, RecoveryManager, RecoveryPolicy
from app.tools.base import Tool
from app.tools.fault_injection import FailureMode, FaultInjectingTool, parse_injection
from app.tools.synthetic import SyntheticSearchProvider
from app.tools.web_search import WebSearchTool
from app.validator import ResultValidator

GOAL = "Analyze the competitive landscape of Voltaic Semiconductors in the AI accelerator market"


class CountingTool(Tool):
    """Real tool stand-in that returns scripted ToolResults and counts calls."""

    def __init__(self, name: str, results: list[ToolResult]) -> None:
        self.name, self.results, self.calls = name, list(results), 0

    def _run(self, **kwargs: Any) -> ToolResult:
        self.calls += 1
        return self.results.pop(0)


def _good_search() -> ToolResult:
    return ToolResult.ok("web_search", {"results": [
        {"title": "A", "url": "https://a.example.com/x", "snippet": "s"}]})


def _manager(tracer, sleeps=None, retries=1):
    sleep = sleeps.append if sleeps is not None else (lambda s: None)
    return RecoveryManager(RecoveryPolicy(max_retries=retries, backoff_s=0.5),
                           ResultValidator(), tracer, sleep=sleep)


# ------------------------------------------------------------------ validator


@pytest.mark.parametrize("data,issue", [
    ({"unexpected": "invalid response"}, 'missing "results"'),
    ({"results": "oops"}, "expected list"),
    ({"results": []}, "0 results"),
    ({"results": [{"title": "x"}, 42]}, "malformed"),
    ({"results": [{"title": "x", "url": "ftp://bad"}]}, "malformed"),
])
def test_search_validator_detects_bad_payloads(data, issue):
    report = ResultValidator().validate(ToolResult(tool="web_search", success=True, data=data))
    assert not report.valid and issue in report.issues[0]


def test_search_validator_keeps_valid_hits_and_warns_about_bad_ones():
    v = ResultValidator()
    r = ToolResult.ok("web_search", {"results": [
        {"title": "ok", "url": "https://ok.example.com"}, {"title": "bad", "url": "localhost"}]})
    report = v.validate(r)
    assert report.valid and len(report.warnings) == 1
    assert [h.url for h in v.search_hits(r)] == ["https://ok.example.com"]


def test_validator_propagates_tool_error_type_and_retryability():
    r = ToolResult.fail("url_fetcher", ErrorType.HTTP_ERROR, "HTTP 404 Not Found", retryable=False)
    report = ResultValidator().validate(r)
    assert not report.valid and report.error_type == ErrorType.HTTP_ERROR and not report.retryable


def test_validator_rejects_success_without_data_and_bad_calculator_result():
    v = ResultValidator()
    assert not v.validate(ToolResult(tool="url_fetcher", success=True, data=None)).valid
    assert not v.validate(ToolResult.ok("url_fetcher", {"text": "short", "url": "https://a.io"})).valid
    assert not v.validate(ToolResult.ok("calculator", {"result": float("inf")})).valid
    assert not v.validate(ToolResult.ok("calculator", {"result": "42"})).valid
    assert v.validate(ToolResult.ok("calculator", {"result": 42.0})).valid


# ------------------------------------------------------------------ recovery manager


def test_malformed_response_is_detected_then_retry_recovers(tracer, state):
    inner = CountingTool("web_search", [_good_search()])
    tool = FaultInjectingTool(inner, FailureMode.MALFORMED, fail_times=1)
    sleeps: list[float] = []
    out = _manager(tracer, sleeps).execute(state=state, task_id=1, tool=tool,
                                          kwargs={"query": "q"}, input_summary='query="q"')
    assert out.ok and out.strategy == "retry" and out.recovered and out.attempts == 2
    assert tool.injected == 1 and inner.calls == 1
    assert sleeps == [0.5]  # backoff actually applied
    assert [e.kind for e in state.events] == ["failure", "recovery"]
    assert 'missing "results"' in state.events[0].message
    assert [c.success for c in state.tool_calls] == [False, True]
    assert any("[ERROR]" in ln and 'missing "results"' in ln for ln in tracer.lines)
    assert any("Retry attempt 1/1" in ln for ln in tracer.lines)


def test_retry_exhausted_then_fallback_provider_recovers(tracer, state):
    primary = FaultInjectingTool(CountingTool("web_search", []), FailureMode.TIMEOUT, fail_times=5)
    backup = WebSearchTool(SyntheticSearchProvider(name="backup"))
    out = _manager(tracer).execute(
        state=state, task_id=1, tool=primary, kwargs={"query": "Voltaic competitors"},
        input_summary="q", fallbacks=[Fallback("backup provider", backup,
                                               {"query": "Voltaic competitors"})])
    assert out.ok and out.strategy == "fallback"
    assert primary.injected == 2  # first try + 1 retry
    assert [e.kind for e in state.events] == ["failure", "failure", "fallback"]
    assert [c.role for c in state.tool_calls] == ["primary", "retry", "fallback"]


def test_non_retryable_error_skips_retry(tracer, state):
    tool = CountingTool("url_fetcher", [
        ToolResult.fail("url_fetcher", ErrorType.HTTP_ERROR, "HTTP 404", retryable=False)])
    out = _manager(tracer).execute(state=state, task_id=4, tool=tool,
                                  kwargs={"url": "https://x.io"}, input_summary="u")
    assert not out.ok and out.strategy == "gave_up" and tool.calls == 1
    assert state.events[-1].kind == "gave_up"


def test_everything_fails_gracefully_without_exception(tracer, state):
    tool = FaultInjectingTool(CountingTool("web_search", []), FailureMode.CRASH, fail_times=9)
    out = _manager(tracer, retries=2).execute(state=state, task_id=1, tool=tool,
                                             kwargs={"query": "q"}, input_summary="q")
    assert not out.ok and out.attempts == 3
    assert all("injected tool crash" in e for e in out.errors)  # crash converted to ToolResult


def test_parse_injection_spec():
    assert parse_injection("web_search:malformed") == ("web_search", FailureMode.MALFORMED, 1)
    assert parse_injection("url_fetcher:timeout:2") == ("url_fetcher", FailureMode.TIMEOUT, 2)
    with pytest.raises(ValueError):
        parse_injection("web_search:explode")


# ------------------------------------------------------------------ end-to-end


def test_agent_recovers_from_injected_malformed_search(settings, tracer):
    agent = build_agent(settings, tracer, offline=True,
                        injections=[("web_search", FailureMode.MALFORMED, 1)])
    result = agent.run(GOAL)
    r = result.report
    assert r.status == "completed"
    assert r.failures >= 1 and r.recoveries >= 1
    assert r.tasks[0].status == "completed_with_recovery"
    assert any('missing "results"' in e.message for e in r.events if e.kind == "failure")
    assert r.sources_analyzed > 0
    assert "Failures and recoveries" in result.markdown


def test_agent_uses_secondary_provider_when_retry_also_fails(settings, tracer):
    agent = build_agent(settings, tracer, offline=True,
                        injections=[("web_search", FailureMode.MALFORMED, 2)])
    r = agent.run(GOAL).report
    assert any(e.kind == "fallback" and "secondary search provider" in e.message for e in r.events)
    assert r.status == "completed"


def test_fetch_timeouts_degrade_to_search_snippets(settings, tracer):
    agent = build_agent(settings, tracer, offline=True,
                        injections=[("url_fetcher", FailureMode.TIMEOUT, 2)])
    r = agent.run(GOAL).report
    assert r.sources[0].retrieval == "snippet_only"
    assert any("using search snippet" in e.message for e in r.events)
    assert r.status == "completed"


def test_agent_fails_gracefully_when_no_data_exists(settings, tracer):
    agent = build_agent(settings, tracer, offline=True)
    result = agent.run("Analyze the competitive landscape of Zzyzx Quux Industries")
    r = result.report
    assert r.status == "failed" and r.sources_analyzed == 0
    assert r.tasks_failed >= 3
    assert "No report could be produced" in r.report.executive_summary
    assert "## Agent Execution Summary" in result.markdown


def test_relevance_filter_drops_generic_off_topic_hits():
    from app.models.tool_result import SearchHit
    from app.validator import is_relevant, relevance_terms
    terms = relevance_terms(["NVIDIA"], "AI accelerator market")
    assert terms == {"nvidia", "accelerator"}
    assert not is_relevant(SearchHit(title="OpenAI | Research & Deployment",
                                     url="https://openai.com/"), terms)
    assert is_relevant(SearchHit(title="AI accelerators market report",
                                 url="https://example.com/r"), terms)
    assert is_relevant(SearchHit(title="x", url="https://blogs.nvidia.com/blog"), terms)
