from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.llm import LLMError  # noqa: E402
from app.models.plan import Plan  # noqa: E402
from app.models.state import ExecutionState  # noqa: E402
from app.planner import TemplatePlanner  # noqa: E402
from app.tracing import Tracer  # noqa: E402


class FakeLLM:
    """Scripted LLM: returns (or raises) the queued responses in order."""

    name = "fake:test"

    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        self.calls.append((system, prompt))
        if not self.responses:
            raise LLMError("no scripted response left")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    """Tests must never depend on the developer's .env, API keys or a running Ollama."""
    monkeypatch.setenv("CI_AGENT_SKIP_DOTENV", "1")
    for var in ("LLM_PROVIDER", "OLLAMA_MODEL", "OLLAMA_BASE_URL", "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY", "TAVILY_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def tracer() -> Tracer:
    return Tracer(quiet=True)


@pytest.fixture
def settings() -> Settings:
    return Settings(retry_backoff_s=0.0)


@pytest.fixture
def plan() -> Plan:
    return TemplatePlanner().create_plan(
        "Analyze the competitive landscape of Voltaic Semiconductors in the AI accelerator market")


@pytest.fixture
def state(plan: Plan) -> ExecutionState:
    return ExecutionState(plan=plan)


@pytest.fixture
def no_sleep():
    calls: list[float] = []
    return calls.append, calls
