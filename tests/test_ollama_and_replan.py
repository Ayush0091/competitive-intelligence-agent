"""Local-LLM (Ollama) client, LLM-driven end-to-end run and reasoning-level re-planning."""

import json

import httpx
import pytest

from app.agent import build_agent
from app.config import Settings
from app.llm import LLMError, OllamaClient, extract_json
from tests.conftest import FakeLLM


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------ Ollama client


def test_ollama_uses_native_chat_with_json_mode_and_context():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"a": 1}'}})

    c = OllamaClient("qwen2.5:7b", "http://localhost:11434/v1", num_ctx=16384,
                     client=_client(handler))
    assert extract_json(c.complete("sys", "hi")) == {"a": 1}
    assert seen["url"] == "http://localhost:11434/api/chat"  # /v1 suffix tolerated
    body = seen["body"]
    assert body["format"] == "json" and body["stream"] is False
    assert body["think"] is False  # Qwen3 reasoning disabled for fast JSON answers
    assert body["options"]["num_ctx"] == 16384 and body["model"] == "qwen2.5:7b"
    assert body["messages"][0] == {"role": "system", "content": "sys"}


def test_ollama_errors_are_actionable():
    def refused(req):
        raise httpx.ConnectError("refused", request=req)
    with pytest.raises(LLMError, match="Ollama not reachable"):
        OllamaClient("qwen3:8b", client=_client(refused)).complete("s", "p")
    with pytest.raises(LLMError, match="ollama pull qwen3:8b"):
        OllamaClient("qwen3:8b", client=_client(lambda r: httpx.Response(404))).complete("s", "p")


def test_ollama_check_reports_installed_and_missing_models():
    tags = {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2:latest"}]}
    ok = OllamaClient("qwen2.5:7b", client=_client(lambda r: httpx.Response(200, json=tags)))
    assert ok.check()[0]
    latest = OllamaClient("llama3.2", client=_client(lambda r: httpx.Response(200, json=tags)))
    assert latest.check()[0]
    missing = OllamaClient("qwen3:14b", client=_client(lambda r: httpx.Response(200, json=tags)))
    good, msg = missing.check()
    assert not good and "qwen2.5:7b" in msg


def test_extract_json_strips_qwen3_think_blocks():
    reply = '<think>The user wants a plan. {"not": "this"}</think>\n{"query": "x", "reason": "y"}'
    assert extract_json(reply) == {"query": "x", "reason": "y"}


def test_settings_select_ollama_without_any_api_key(monkeypatch):
    for var in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_MODEL",
                "LLM_BASE_URL", "OLLAMA_BASE_URL", "LLM_TIMEOUT_S"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:14b")
    s = Settings.from_env(load_env_file=False)
    assert (s.llm_provider, s.llm_model, s.llm_base_url) == (
        "ollama", "qwen2.5:14b", "http://localhost:11434")
    assert s.llm_timeout_s == 300.0 and s.llm_api_key is None


def test_unreachable_ollama_degrades_to_deterministic_mode(monkeypatch, tracer):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # nothing listens here
    settings = Settings.from_env(load_env_file=False)
    agent = build_agent(settings, tracer, offline=True)
    assert agent.llm_name == "none"
    assert any("LLM health check" in ln for ln in tracer.lines)
    assert agent.run("Analyze the competitive landscape of Voltaic Semiconductors").report.status \
        == "completed"


# ------------------------------------------------------------------ LLM-driven run

def _plan(tasks, targets=("Voltaic Semiconductors",)):
    return json.dumps({"objective": {"target_entities": list(targets), "analysis_type": "landscape",
                                     "market": "AI accelerators"}, "tasks": tasks})


GOOD_PLAN = _plan([
    {"id": 1, "description": "Find competitors", "tool": "web_search",
     "query": "Voltaic Semiconductors rivals", "depends_on": [], "max_items": 4},
    {"id": 2, "description": "Read sources", "tool": "url_fetcher", "query": None,
     "depends_on": [1], "max_items": 3},
    {"id": 3, "description": "Compute metrics", "tool": "calculator", "query": None,
     "depends_on": [2], "max_items": 3},
    {"id": 4, "description": "Write brief", "tool": "synthesize", "query": None,
     "depends_on": [2, 3], "max_items": 3},
])


def test_end_to_end_with_llm_brain(settings, tracer):
    metrics = json.dumps({"figures": [
        {"entity": "Voltaic", "metric": "data-center revenue", "value": 18.4,
         "unit": "billion USD", "period": "fiscal 2025", "source_id": 1},
        {"entity": "Voltaic", "metric": "data-center revenue", "value": 10.2,
         "unit": "billion USD", "period": "fiscal 2024", "source_id": 1}]})
    synth = json.dumps({
        "executive_summary": "Voltaic leads; Nimbus is the closest challenger.",
        "competitors": [{"name": "Nimbus Compute", "summary": "Lower-cost MX3 challenger.",
                         "source_ids": [1], "kind": "fact"}],
        "recent_developments": [{"text": "Voltaic partnered with Orbital Networks.",
                                 "source_ids": [2], "kind": "fact"}],
        "market_signals": [{"text": "Price competition likely to intensify.",
                            "source_ids": [], "kind": "inference"}],
        "risks": [{"text": "Export rules could affect revenue.", "source_ids": [77],
                   "kind": "fact"}],
    })
    llm = FakeLLM(GOOD_PLAN, metrics, synth)
    r = build_agent(settings, tracer, offline=True, llm=llm).run("Who competes with Voltaic?").report
    assert r.planner == "llm" and r.llm == "fake:test"
    assert any(ln.startswith("[LLM] fake:test answered in") for ln in tracer.lines)
    assert r.report.synthesis_method.startswith("llm")
    assert r.metrics[0].value == pytest.approx(80.39, rel=1e-3)  # computed by the calculator
    # invented citation [77] removed -> fact downgraded to inference
    assert r.report.risks[0].kind == "inference" and r.report.risks[0].source_ids == []
    assert r.status == "completed"


def test_llm_replans_a_search_that_failed_all_tool_level_recovery(settings, tracer):
    plan = _plan([
        {"id": 1, "description": "Find Zzyzx market share", "tool": "web_search",
         "query": "Zzyzx Corp market share", "depends_on": [], "max_items": 4},
        {"id": 2, "description": "Read sources", "tool": "url_fetcher", "query": None,
         "depends_on": [1], "max_items": 3},
        {"id": 3, "description": "Write brief", "tool": "synthesize", "query": None,
         "depends_on": [2], "max_items": 3},
    ], targets=("Zzyzx Corp",))
    replan = json.dumps({"query": "Voltaic Semiconductors competitors",
                         "reason": "Zzyzx has no coverage; research its known rival instead"})
    llm = FakeLLM(plan, replan)  # later LLM calls fail -> extractive fallback is exercised too
    r = build_agent(settings, tracer, offline=True, llm=llm).run("Analyze Zzyzx Corp").report
    kinds = [e.kind for e in r.events]
    assert "replan" in kinds
    assert r.tasks[0].status == "completed_with_recovery" and "re-plan" in r.tasks[0].note
    assert r.sources_analyzed > 0
    assert any("[REPLAN]" in ln and "Voltaic Semiconductors competitors" in ln for ln in tracer.lines)
    # the re-planner was given the failed queries as context
    assert "Zzyzx Corp market share" in llm.calls[1][1]


def test_replanner_that_repeats_a_failed_query_is_rejected(settings, tracer):
    plan = _plan([
        {"id": 1, "description": "Find Zzyzx news", "tool": "web_search",
         "query": "Zzyzx Corp news", "depends_on": [], "max_items": 4},
        {"id": 2, "description": "Read sources", "tool": "url_fetcher", "query": None,
         "depends_on": [1], "max_items": 3},
        {"id": 3, "description": "Write brief", "tool": "synthesize", "query": None,
         "depends_on": [2], "max_items": 3},
    ], targets=("Zzyzx Corp",))
    llm = FakeLLM(plan, json.dumps({"query": "zzyzx corp NEWS", "reason": "try again"}))
    r = build_agent(settings, tracer, offline=True, llm=llm).run("Analyze Zzyzx Corp").report
    assert r.tasks[0].status == "failed"
    assert any("repeated a query" in e.message for e in r.events)
    assert r.status == "failed"


def test_auto_model_prefers_installed_qwen():
    tags = {"models": [{"name": "nomic-embed-text:latest"}, {"name": "llama3.2:latest"},
                       {"name": "qwen2.5:7b"}]}
    c = OllamaClient("auto", client=_client(lambda r: httpx.Response(200, json=tags)))
    assert c.resolve_auto_model() == "qwen2.5:7b" and c.name == "ollama:qwen2.5:7b"
    none = OllamaClient("auto", client=_client(lambda r: httpx.Response(200, json={"models": []})))
    assert none.resolve_auto_model() is None
