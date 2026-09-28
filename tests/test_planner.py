import json

import pytest
from pydantic import ValidationError

from app.models.plan import AnalysisType, Objective, Plan, Task
from app.planner import (
    LLMPlanner,
    PlanningError,
    TemplatePlanner,
    extract_entities,
    interpret_goal,
    render_plan,
)
from tests.conftest import FakeLLM

# ---------------------------------------------------------------- interpretation


def test_interpret_landscape_goal():
    obj = interpret_goal("Analyze the competitive landscape of NVIDIA in the AI accelerator market.")
    assert obj.target_entities == ["NVIDIA"]
    assert obj.analysis_type == AnalysisType.LANDSCAPE
    assert obj.market == "AI accelerator market"


def test_interpret_comparison_goal():
    obj = interpret_goal("Compare NVIDIA and AMD in AI accelerators")
    assert obj.target_entities == ["NVIDIA", "AMD"]
    assert obj.analysis_type == AnalysisType.COMPARISON
    assert obj.market == "AI accelerators"


def test_interpret_developments_goal_with_possessive_and_multiword_name():
    obj = interpret_goal("Research recent developments of Helix Silicon's inference business")
    assert obj.target_entities == ["Helix Silicon"]
    assert obj.analysis_type == AnalysisType.DEVELOPMENTS


def test_interpret_topic_goal_without_named_entity():
    obj = interpret_goal("summarize recent developments in solid-state batteries")
    assert obj.target_entities and "solid-state batteries" in obj.target_entities[0]


def test_interpret_rejects_tiny_goal():
    with pytest.raises(PlanningError):
        interpret_goal("hi")


def test_extract_entities_ignores_lead_verbs_and_generic_caps():
    assert extract_entities("Analyze AI chips from Quanta Forge Labs") == ["Quanta Forge Labs"]


# ---------------------------------------------------------------- template plans


@pytest.mark.parametrize("goal,n_search", [
    ("Analyze the competitive landscape of NVIDIA in the AI accelerator market", 3),
    ("Compare NVIDIA, AMD and Intel in AI accelerators", 4),  # 1 head-to-head + 3 per-company
    ("Research recent developments of Helix Silicon", 3),
])
def test_template_plan_is_valid_and_ordered(goal, n_search):
    plan = TemplatePlanner().create_plan(goal)
    tools = [t.tool for t in plan.tasks]
    assert tools.count("web_search") == n_search
    assert tools[-3:] == ["url_fetcher", "calculator", "synthesize"]
    assert plan.tools_used() == ["web_search", "url_fetcher", "calculator"]
    assert all(t.query for t in plan.tasks if t.tool == "web_search")
    # queries are built from the goal, not hard-coded
    assert all(plan.objective.target_entities[0] in (t.query or "")
               for t in plan.tasks if t.tool == "web_search"
               and plan.objective.analysis_type != AnalysisType.COMPARISON)


def test_template_queries_do_not_duplicate_market_word(plan):
    assert all("market market" not in (t.query or "") for t in plan.tasks)


# ---------------------------------------------------------------- plan validation

_OBJ = Objective(raw_goal="g", target_entities=["X"])


def _tasks(*specs):
    return [Task(**s) for s in specs]


def test_plan_rejects_missing_final_synthesize():
    with pytest.raises(ValidationError, match="synthesize"):
        Plan(goal="g", objective=_OBJ, tasks=_tasks(
            {"id": 1, "description": "search", "tool": "web_search", "query": "x"},
            {"id": 2, "description": "fetch", "tool": "url_fetcher", "depends_on": [1]}))


def test_plan_rejects_forward_dependency():
    with pytest.raises(ValidationError, match="invalid/later"):
        Plan(goal="g", objective=_OBJ, tasks=_tasks(
            {"id": 1, "description": "search", "tool": "web_search", "query": "x"},
            {"id": 2, "description": "fetch", "tool": "url_fetcher", "depends_on": [3]},
            {"id": 3, "description": "write", "tool": "synthesize", "depends_on": [2]}))


def test_task_rejects_search_without_query():
    with pytest.raises(ValidationError, match="query"):
        Task(id=1, description="search", tool="web_search")


def test_plan_rejects_fetch_not_depending_on_search():
    with pytest.raises(ValidationError, match="url_fetcher must depend"):
        Plan(goal="g", objective=_OBJ, tasks=_tasks(
            {"id": 1, "description": "search", "tool": "web_search", "query": "x"},
            {"id": 2, "description": "calc", "tool": "calculator", "depends_on": [1]},
            {"id": 3, "description": "fetch", "tool": "url_fetcher", "depends_on": [2]},
            {"id": 4, "description": "write", "tool": "synthesize", "depends_on": [3]}))


def test_plan_rejects_unknown_tool():
    with pytest.raises(ValidationError):
        Task(id=1, description="hack", tool="shell", query="rm -rf /")


# ---------------------------------------------------------------- LLM planner

VALID_LLM_PLAN = json.dumps({
    "objective": {"target_entities": ["NVIDIA"], "analysis_type": "landscape",
                  "market": "AI accelerators"},
    "tasks": [
        {"id": 1, "description": "Find competitors", "tool": "web_search",
         "query": "NVIDIA AI accelerator competitors", "depends_on": [], "max_items": 5},
        {"id": 2, "description": "Find news", "tool": "web_search",
         "query": "NVIDIA news", "depends_on": [], "max_items": 5},
        {"id": 3, "description": "Read sources", "tool": "url_fetcher", "depends_on": [1, 2],
         "max_items": 4},
        {"id": 4, "description": "Compute metrics", "tool": "calculator", "depends_on": [3]},
        {"id": 5, "description": "Write report", "tool": "synthesize", "depends_on": [3, 4]},
    ],
})


def test_llm_planner_accepts_valid_plan_in_code_fence(tracer):
    planner = LLMPlanner(FakeLLM(f"Here you go:\n```json\n{VALID_LLM_PLAN}\n```"), tracer)
    plan = planner.create_plan("Analyze NVIDIA")
    assert plan.planner == "llm"
    assert len(plan.tasks) == 5
    assert planner.events == []


def test_llm_planner_retries_with_error_feedback_then_succeeds(tracer):
    bad = json.dumps({"objective": {"target_entities": ["NVIDIA"]},
                      "tasks": [{"id": 1, "description": "search", "tool": "web_search"}]})
    llm = FakeLLM(bad, VALID_LLM_PLAN)
    planner = LLMPlanner(llm, tracer)
    plan = planner.create_plan("Analyze NVIDIA")
    assert plan.planner == "llm"
    assert "previous plan was invalid" in llm.calls[1][1]
    assert [k for k, _ in planner.events] == ["failure", "recovery"]


def test_llm_planner_falls_back_to_template_on_garbage(tracer):
    planner = LLMPlanner(FakeLLM("not json at all", "{still: broken"), tracer)
    plan = planner.create_plan("Analyze the competitive landscape of NVIDIA")
    assert plan.planner == "template"
    assert [k for k, _ in planner.events] == ["failure", "failure", "fallback"]


def test_render_plan_shows_tasks_and_tools(plan):
    text = render_plan(plan, max_retries=1)
    assert "AGENT EXECUTION PLAN" in text
    for t in plan.tasks:
        assert f"[{t.id}] {t.description}" in text
    assert "✓ Web Search" in text and "✓ Calculator" in text
    assert "recovery enabled" in text
