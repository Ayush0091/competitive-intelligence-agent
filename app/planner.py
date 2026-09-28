"""Goal interpretation and plan generation.

Two strategies behind one interface:
  * LLMPlanner       – asks the LLM for a JSON plan, validates it with Pydantic,
                       retries once with the validation error, then falls back.
  * TemplatePlanner  – deterministic, rule-based objective parsing + plan
                       templates. Used when no LLM is configured and as the
                       fallback when the LLM's plan is invalid.
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import ValidationError

from app.llm import LLMClient, LLMError, extract_json
from app.models.plan import AnalysisType, Objective, Plan, Task
from app.models.state import ExecutionState
from app.tracing import Tracer


class PlanningError(Exception):
    pass


class Planner(Protocol):
    def create_plan(self, goal: str) -> Plan: ...


# ---------------------------------------------------------------------------
# Rule-based goal interpretation
# ---------------------------------------------------------------------------
_LEAD_WORDS = {
    "analyze", "analyse", "compare", "research", "produce", "give", "write", "create",
    "summarize", "summarise", "investigate", "assess", "evaluate", "provide", "show",
    "find", "make", "prepare", "build", "generate", "what", "how", "who", "tell",
    "explain", "please", "can", "could", "list", "identify", "describe", "review",
}
_NON_ENTITY_CAPS = {
    "ai", "the", "a", "an", "in", "of", "and", "or", "for", "on", "with", "to", "vs",
    "versus", "market", "markets", "competitive", "competition", "landscape", "brief",
    "report", "i", "me", "my", "using", "public", "web", "data", "recent", "latest",
    "top", "short", "developments", "news", "industry", "sector", "company", "companies",
    "ceo", "q1", "q2", "q3", "q4", "gpu", "gpus", "llm", "llms", "us", "eu", "uk",
}
_COMPARISON_RE = re.compile(r"\b(compare|comparison|versus|vs\.?|against|head[- ]to[- ]head)\b", re.I)
_DEVELOPMENT_RE = re.compile(r"\b(recent|develop\w*|news|latest|announce\w*|updates?)\b", re.I)
_LANDSCAPE_RE = re.compile(r"\b(compet\w*|landscape|rivals?)\b", re.I)
_MARKET_RE = re.compile(
    r"\b(?:in|within|across)\s+(?:the\s+)?([\w\s\-/&]{2,60}?)\s+(market|industry|sector|space)\b", re.I
)
_TRAILING_IN_RE = re.compile(r"\bin\s+(?:the\s+)?([\w\s\-/&]{3,50}?)\s*[.?!]?\s*$", re.I)


def _clean_token(tok: str) -> str:
    tok = re.sub(r"(['’]s)$", "", tok)
    return tok.strip(".,;:!?()\"'’“”")


def extract_entities(goal: str) -> list[str]:
    """Pull capitalised name sequences (e.g. 'NVIDIA', 'Voltaic Semiconductors')."""
    entities: list[str] = []
    current: list[str] = []
    words = goal.split()
    for idx, raw in enumerate(words):
        tok = _clean_token(raw)
        low = tok.lower()
        is_name = bool(tok) and (tok[0].isupper() or (tok[0].isdigit() and any(c.isupper() for c in tok)))
        is_name = is_name and low not in _NON_ENTITY_CAPS and not (idx == 0 and low in _LEAD_WORDS)
        if is_name:
            current.append(tok)
        if not is_name or raw.rstrip().endswith((",", ";", ":")) or tok != raw.strip("\"'"):
            # a name sequence ends at a non-name token or at punctuation / possessive
            if current:
                name = " ".join(current)
                if name not in entities:
                    entities.append(name)
                current = []
    if current:
        name = " ".join(current)
        if name not in entities:
            entities.append(name)
    return entities[:5]


def extract_market(goal: str) -> str | None:
    m = _MARKET_RE.search(goal)
    if m:
        return f"{m.group(1).strip()} {m.group(2).lower()}"
    m = _TRAILING_IN_RE.search(goal)
    if m:
        return m.group(1).strip()
    return None


def interpret_goal(goal: str) -> Objective:
    goal = goal.strip()
    if len(goal) < 5:
        raise PlanningError("goal is too short to interpret")
    entities = extract_entities(goal)
    if _COMPARISON_RE.search(goal) or len(entities) >= 2 and " and " in goal.lower():
        analysis = AnalysisType.COMPARISON if len(entities) >= 2 else AnalysisType.LANDSCAPE
    elif _DEVELOPMENT_RE.search(goal) and not _LANDSCAPE_RE.search(goal):
        analysis = AnalysisType.DEVELOPMENTS
    else:
        analysis = AnalysisType.LANDSCAPE
    if not entities:  # topic-style goal, e.g. "recent developments in solid-state batteries"
        words = [w for w in goal.rstrip(".?!").split() if w.lower() not in _LEAD_WORDS]
        entities = [" ".join(words)[:60] or goal[:60]]
    return Objective(
        raw_goal=goal, target_entities=entities, analysis_type=analysis, market=extract_market(goal)
    )


# ---------------------------------------------------------------------------
# Template planner
# ---------------------------------------------------------------------------
class TemplatePlanner:
    """Deterministic planner: rule-based objective + analysis-type templates."""

    def create_plan(self, goal: str, objective: Objective | None = None) -> Plan:
        obj = objective or interpret_goal(goal)
        core = re.sub(r"\s+(market|industry|sector|space)$", "", obj.market or "", flags=re.I)
        market = f" {core}" if core else ""
        t = obj.primary
        specs: list[tuple[str, str]]  # (description, query)
        if obj.analysis_type == AnalysisType.COMPARISON:
            others = obj.target_entities[1:]
            specs = [(f"Find head-to-head comparisons of {t} and {', '.join(others)}",
                      f"{t} vs {' vs '.join(others)}{market}")]
            specs += [(f"Research recent developments for {e}", f"{e}{market} recent developments")
                      for e in obj.target_entities]
        elif obj.analysis_type == AnalysisType.DEVELOPMENTS:
            specs = [(f"Research recent developments for {t}", f"{t}{market} recent developments"),
                     (f"Find recent announcements and product news for {t}", f"{t} announcements news"),
                     (f"Find competitive context for {t}", f"{t} competitors{market}")]
        else:
            specs = [(f"Identify major competitors of {t}", f"{t} competitors{market}"),
                     (f"Research recent developments for {t}", f"{t}{market} recent developments"),
                     (f"Find market-share and financial signals for {t}",
                      f"{t}{market} market share revenue")]

        tasks = [Task(id=i + 1, description=d, tool="web_search", query=q, max_items=5)
                 for i, (d, q) in enumerate(specs)]
        search_ids = [task.id for task in tasks]
        n = len(tasks)
        tasks += [
            Task(id=n + 1, tool="url_fetcher", depends_on=search_ids, max_items=5,
                 description="Retrieve and read the most relevant public sources"),
            Task(id=n + 2, tool="calculator", depends_on=[n + 1],
                 description="Compute comparable metrics from figures stated in sources"),
            Task(id=n + 3, tool="synthesize", depends_on=[n + 1, n + 2],
                 description="Synthesize validated evidence into the final report"),
        ]
        return Plan(goal=goal, objective=obj, tasks=tasks, planner="template")


# ---------------------------------------------------------------------------
# LLM planner
# ---------------------------------------------------------------------------
PLANNER_SYSTEM = """You are the planning module of a competitive-intelligence agent.
Convert the user's goal into a structured objective and a short sequential task plan.
Return ONLY a JSON object, no prose.

Available tools:
- web_search: needs "query" (a concise search-engine query).
- url_fetcher: reads full pages for the top results of earlier web_search tasks.
  Needs "depends_on" listing those web_search task ids and "max_items" (1-6).
- calculator: computes metrics from numbers stated in fetched sources.
  Needs "depends_on" = [the url_fetcher task id].
- synthesize: writes the final report. Must be the LAST task, exactly once,
  with "depends_on" listing the url_fetcher (and calculator) task ids.

Rules: 5-9 tasks, ids sequential from 1, depends_on may only reference earlier ids,
2-4 web_search tasks with distinct queries, no company-specific assumptions beyond the goal.

Tailor the web_search queries to what THIS goal needs (e.g. a comparison needs head-to-head
and per-company queries; a "recent developments" goal needs news-style queries; a market
question needs market-share / competitor queries). Keep queries short (3-8 words).

JSON schema:
{"objective": {"target_entities": [str], "analysis_type": "landscape|comparison|developments",
               "market": str|null},
 "tasks": [{"id": int, "description": str, "tool": str, "query": str|null,
            "depends_on": [int], "max_items": int}]}

Example for the goal "How is Acme Robotics positioned against rivals in warehouse automation?":
{"objective": {"target_entities": ["Acme Robotics"], "analysis_type": "landscape",
               "market": "warehouse automation"},
 "tasks": [
  {"id": 1, "description": "Identify Acme Robotics' main competitors", "tool": "web_search",
   "query": "Acme Robotics competitors warehouse automation", "depends_on": [], "max_items": 5},
  {"id": 2, "description": "Find Acme Robotics' recent news", "tool": "web_search",
   "query": "Acme Robotics news 2026", "depends_on": [], "max_items": 5},
  {"id": 3, "description": "Find market size and share data", "tool": "web_search",
   "query": "warehouse automation market share leaders", "depends_on": [], "max_items": 5},
  {"id": 4, "description": "Read the most relevant sources", "tool": "url_fetcher",
   "query": null, "depends_on": [1, 2, 3], "max_items": 5},
  {"id": 5, "description": "Compute comparable metrics", "tool": "calculator",
   "query": null, "depends_on": [4], "max_items": 3},
  {"id": 6, "description": "Write the competitive brief", "tool": "synthesize",
   "query": null, "depends_on": [4, 5], "max_items": 3}]}"""


class LLMPlanner:
    """LLM planning with validation, one corrective retry, then template fallback."""

    def __init__(
        self, llm: LLMClient, tracer: Tracer, fallback: TemplatePlanner | None = None,
        max_retries: int = 1,
    ) -> None:
        self.llm, self.tracer = llm, tracer
        self.fallback = fallback or TemplatePlanner()
        self.max_retries = max_retries
        self.events: list[tuple[str, str]] = []  # (kind, message) copied into run state

    def create_plan(self, goal: str) -> Plan:
        prompt = f"Goal: {goal}"
        last_error = ""
        for attempt in range(1, self.max_retries + 2):
            try:
                raw = self.llm.complete(PLANNER_SYSTEM, prompt)
                data = extract_json(raw)
                obj = Objective(raw_goal=goal, **(data.get("objective") or {}))
                plan = Plan(goal=goal, objective=obj, tasks=data.get("tasks") or [], planner="llm")
                if attempt > 1:
                    self._event("recovery", f"LLM plan valid after corrective retry {attempt - 1}")
                return plan
            except (LLMError, ValidationError, TypeError) as e:
                last_error = _short_error(e)
                self._event("failure", f"LLM plan rejected (attempt {attempt}): {last_error}")
                prompt = (f"Goal: {goal}\n\nYour previous plan was invalid: {last_error}\n"
                          "Return a corrected JSON plan that satisfies every rule.")
        self._event("fallback", "Falling back to deterministic template planner")
        return self.fallback.create_plan(goal)

    def _event(self, kind: str, message: str) -> None:
        tag = {"failure": "VALIDATION", "recovery": "RECOVERY", "fallback": "RECOVERY"}[kind]
        self.tracer.log(tag, message, component="planner")
        self.events.append((kind, message))

    def copy_events_to(self, state: ExecutionState) -> None:
        for kind, message in self.events:
            state.record_event(kind, message, tool="planner")


def _short_error(e: Exception) -> str:
    if isinstance(e, ValidationError):
        errs = e.errors()
        first = errs[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        return f"{len(errs)} validation error(s); first: {loc} {first.get('msg', '')}".strip()
    return str(e)[:200]


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
_TOOL_LABELS = {"web_search": "Web Search", "url_fetcher": "URL Fetcher", "calculator": "Calculator"}


def render_plan(plan: Plan, *, max_retries: int, planner_note: str = "",
                replanning: bool = False) -> str:
    bar = "=" * 60
    obj = plan.objective
    lines = [bar, "AGENT EXECUTION PLAN", bar, "", "Goal:", f"  {plan.goal}", "",
             "Interpreted objective:",
             f"  type={obj.analysis_type.value}  targets={', '.join(obj.target_entities)}"
             f"  market={obj.market or 'n/a'}", "",
             f"Planner: {plan.planner}{f' ({planner_note})' if planner_note else ''}", "", "Tasks:"]
    for t in plan.tasks:
        detail = f'query="{t.query}"' if t.query else f"inputs from tasks {t.depends_on}"
        lines.append(f"  [{t.id}] {t.description}")
        lines.append(f"       -> {t.tool} ({detail})")
    lines += ["", "Tools:"]
    lines += [f"  ✓ {_TOOL_LABELS[name]}" for name in plan.tools_used()]
    lines += ["", "Execution mode:",
              f"  Sequential | every tool result validated | recovery enabled "
              f"(retries={max_retries}, fallbacks on"
              f"{', LLM re-planning on' if replanning else ''})", bar]
    return "\n".join(lines)
