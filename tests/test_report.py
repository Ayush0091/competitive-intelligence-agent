import json

from app.agent import build_agent
from app.metrics import (LLMMetricExtractor, MetricRequest, RegexMetricExtractor,
                         is_grounded, is_well_formed)
from app.models.plan import Objective
from app.models.report import Source
from app.synthesizer import ExtractiveSynthesizer, LLMSynthesizer
from app.validator import ResultValidator
from tests.conftest import FakeLLM

GOAL = "Compare Voltaic Semiconductors and Nimbus Compute in AI accelerators"
SECTIONS = ["# Competitive Landscape Report", "## Target Company", "## Executive Summary",
            "## Major Competitors", "## Recent Developments", "## Competitive Signals",
            "## Risks / Challenges", "## Sources", "## Agent Execution Summary"]


def _sources() -> list[Source]:
    return [
        Source(id=1, url="https://a.example.com", title="A", origin_task=4,
               text="Acme reported revenue of $4.1 billion in 2025, up from $2.3 billion in 2024. "
                    "Acme launched a new chip that competes with Globex Corp products."),
        Source(id=2, url="https://b.example.com", title="B", origin_task=4,
               text="Globex reported revenue of $10 billion in 2025, up from $8 billion in 2024. "
                    "Export restrictions are a risk for Globex according to analysts."),
    ]


def test_full_report_json_and_markdown(settings, tracer, tmp_path):
    result = build_agent(settings, tracer, offline=True).run(GOAL, output_dir=tmp_path)
    r = result.report
    for heading in SECTIONS:
        assert heading in result.markdown
    assert "OFFLINE SYNTHETIC MODE" in result.markdown
    assert r.tools_used == ["calculator", "url_fetcher", "web_search"]
    assert r.tasks_total == len(r.tasks) == 6 and r.tasks_completed == 6
    # every cited source id exists
    ids = {s.id for s in r.sources}
    for f in r.report.recent_developments + r.report.market_signals + r.report.risks:
        assert set(f.source_ids) <= ids
    # saved files are valid and the JSON omits full page text
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["status"] == "completed" and data["sources_analyzed"] == len(r.sources)
    assert "text" not in data["sources"][0]
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == result.markdown
    # metrics were computed by the calculator tool, not the synthesizer
    assert r.metrics and all(m.status == "ok" for m in r.metrics)
    assert any(c.tool == "calculator" and c.success for c in r.tool_calls)


def test_regex_metrics_growth_and_share():
    obj = Objective(raw_goal="g", target_entities=["Acme", "Globex"])
    ms = RegexMetricExtractor().extract(obj, _sources(), ["Acme", "Globex"])
    labels = [m.label for m in ms]
    assert "Acme: revenue growth vs prior period" in labels
    assert any("share of combined reported revenue" in lbl for lbl in labels)
    growth = next(m for m in ms if m.label.startswith("Acme: revenue growth"))
    assert growth.expression == "(4.1 - 2.3) / 2.3 * 100" and growth.source_ids == [1]


def test_metric_grounding_rejects_numbers_not_in_sources():
    by_id = {s.id: s for s in _sources()}
    ok = MetricRequest(label="growth", expression="(4.1 - 2.3) / 2.3 * 100", source_ids=[1])
    invented = MetricRequest(label="made up", expression="99.9 / 4.1 * 100", source_ids=[1])
    uncited = MetricRequest(label="uncited", expression="4.1 * 2", source_ids=[7])
    assert is_grounded(ok, by_id) == (True, "")
    assert not is_grounded(invented, by_id)[0]
    assert not is_grounded(uncited, by_id)[0]


def test_llm_extracts_figures_and_python_derives_metrics():
    obj = Objective(raw_goal="g", target_entities=["Acme", "Globex"])
    llm = FakeLLM(json.dumps({"figures": [
        {"entity": "Acme", "metric": "revenue", "value": 4.1, "unit": "billion USD",
         "period": "2025", "source_id": 1},
        {"entity": "Acme", "metric": "revenue", "value": 2.3, "unit": "billion USD",
         "period": "2024", "source_id": 1},
        {"entity": "Globex", "metric": "revenue", "value": 10, "unit": "billion USD",
         "period": "2025", "source_id": 2},
        {"entity": "Acme", "metric": "revenue", "value": 99.9, "unit": "billion USD",
         "period": "2023", "source_id": 1},          # not in the source -> dropped
    ]}))
    ex = LLMMetricExtractor(llm)
    metrics = {m.label: m.expression for m in ex.extract(obj, _sources(), ["Acme", "Globex"])}
    assert metrics["Acme revenue: growth 2024 to 2025"] == "(4.1 - 2.3) / 2.3 * 100"
    assert any("share of combined revenue 2025" in k for k in metrics)
    assert any("99.9 not found" in r for r in ex.rejected)
    # the LLM never writes arithmetic, so every derived metric passes the sanity checks
    assert all(is_well_formed(MetricRequest(label=k, expression=v, unit="%"))[0]
               for k, v in metrics.items())
    # unusable LLM output -> deterministic regex extractor
    ex2 = LLMMetricExtractor(FakeLLM("garbage"))
    assert ex2.extract(obj, _sources(), ["Acme", "Globex"])


def test_llm_synthesizer_cannot_invent_sources():
    obj = Objective(raw_goal="g", target_entities=["Acme"])
    reply = json.dumps({
        "executive_summary": "Acme is growing.",
        "competitors": [{"name": "Globex", "summary": "rival", "source_ids": [1, 99], "kind": "fact"}],
        "recent_developments": [{"text": "Acme launched a chip.", "source_ids": [1], "kind": "fact"}],
        "market_signals": [{"text": "Invented claim.", "source_ids": [42], "kind": "fact"}],
        "risks": [{"text": "Export risk.", "source_ids": [2], "kind": "fact"}],
    })
    synth = LLMSynthesizer(FakeLLM(reply), ResultValidator())
    body = synth.synthesize(obj, _sources(), [], [])
    assert body.competitors[0].source_ids == [1]
    assert body.market_signals[0].kind == "inference" and body.market_signals[0].source_ids == []
    assert any("unknown source" in n for n in synth.notes)


def test_llm_synthesizer_falls_back_to_extractive():
    obj = Objective(raw_goal="g", target_entities=["Acme"])
    synth = LLMSynthesizer(FakeLLM("nope", "still nope"), ResultValidator())
    body = synth.synthesize(obj, _sources(), [], ["Globex"])
    assert body.synthesis_method.startswith("extractive")
    assert "Fell back to extractive synthesis" in synth.notes


def test_extractive_findings_are_verbatim_quotes():
    obj = Objective(raw_goal="g", target_entities=["Acme"])
    srcs = _sources()
    body = ExtractiveSynthesizer().synthesize(obj, srcs, [], ["Globex"])
    all_text = " ".join(s.text for s in srcs)
    for f in body.recent_developments + body.market_signals + body.risks:
        assert f.kind == "fact" and f.text in all_text


def test_metric_sanity_checks_catch_real_local_model_mistakes():
    """Cases observed in a live run with qwen3:8b."""
    from app.metrics import is_well_formed
    bare = MetricRequest(label="NVIDIA AI GPU share", expression="86", unit="%")
    fake_cagr = MetricRequest(label="Market CAGR 2026-2031", expression="518.12 / 174.69 - 1",
                              unit="%")
    no_percent = MetricRequest(label="Growth", expression="(5 - 4) / 4", unit="%")
    good_cagr = MetricRequest(label="Market CAGR 2026-2031", unit="%",
                              expression="((518.12 / 174.69) ** (1 / 5) - 1) * 100")
    assert not is_well_formed(bare)[0]
    self_minus = MetricRequest(label="Performance gap", expression="40 - 40", unit="PFLOPS")
    assert "distinct" in is_well_formed(self_minus)[1]
    assert not is_well_formed(fake_cagr)[0]
    assert "100" in is_well_formed(no_percent)[1]
    assert is_well_formed(good_cagr) == (True, "")


def test_relevant_excerpt_prefers_on_topic_lines_within_budget():
    from app.text_utils import relevant_excerpt
    text = "\n".join([
        "Accept cookies to continue browsing this website today please thanks",
        "Home | Products | About us | Careers | Contact | Investors | Newsroom",
        "NVIDIA reported data-center revenue of $41.1 billion in the quarter.",
        "Subscribe to our newsletter for the latest updates and special offers",
        "AMD said its MI350 accelerator is ramping with major cloud customers.",
    ])
    out = relevant_excerpt(text, {"nvidia", "accelerator"}, max_chars=150)
    assert out.splitlines() == [
        "NVIDIA reported data-center revenue of $41.1 billion in the quarter.",
        "AMD said its MI350 accelerator is ramping with major cloud customers."]


def test_fact_with_figure_missing_from_cited_source_becomes_inference():
    """Seen live: the model cited S3 for a CAGR that the agent itself had computed."""
    from app.models.report import Finding, ReportBody
    body = ReportBody(target_company="X", executive_summary="", market_signals=[
        Finding(text="The market will grow at a CAGR of 24.29% to 2031.", source_ids=[3]),
        Finding(text="Revenue reached $518.12 billion by 2031.", source_ids=[3]),
    ])
    texts = {3: "The market is forecast to reach USD 518.12 billion in 2031."}
    body, issues = ResultValidator.enforce_citations(body, {3}, texts)
    assert body.market_signals[0].kind == "inference" and "24.29" in issues[0]
    assert body.market_signals[1].kind == "fact"  # 518.12 is in the source; 2031 is a year


def test_derive_metrics_growth_cagr_pp_and_share():
    from app.metrics import Figure, derive_metrics
    from app.tools.calculator import safe_eval
    figs = [
        Figure(entity="Market", metric="market size", value=140.55, unit="billion USD",
               period="2025", source_id=3),
        Figure(entity="Market", metric="market size", value=518.12, unit="billion USD",
               period="2031", source_id=3),
        Figure(entity="NVIDIA", metric="market share", value=86, unit="%", period="2025",
               source_id=1),
        Figure(entity="NVIDIA", metric="market share", value=75, unit="%", period="2028",
               source_id=1),
    ]
    got = {m.label: round(safe_eval(m.expression), 2) for m in derive_metrics(figs)}
    assert got["market size: CAGR 2025 to 2031"] == 24.29
    assert got["NVIDIA market share: change 2025 to 2028"] == -11.0  # percentage points
    assert "market size: growth 2025 to 2031" in got


def test_report_explains_why_no_metrics_were_computed():
    from app.models.report import TaskSummary
    from app.reporter import render_markdown
    from datetime import datetime
    from app.models.state import ExecutionState
    from app.planner import TemplatePlanner
    from app.reporter import build_run_report
    plan = TemplatePlanner().create_plan("Analyze the competitive landscape of Acme")
    state = ExecutionState(plan=plan)
    state.task_summaries[5] = TaskSummary(id=5, description="calc", tool="calculator",
                                          status="skipped",
                                          note="all 6 proposed metric(s) failed validation")
    md = render_markdown(build_run_report(state, started_at=datetime.now(), duration_s=1,
                                          llm_name="none"))
    assert "No metrics were computed: all 6 proposed metric(s) failed validation" in md


def test_metric_unit_sanity_from_tavily_live_run():
    """Nonsense metrics qwen3:8b produced in a live run with Tavily search."""
    from app.metrics import is_well_formed
    ratio_in_gb = MetricRequest(label="MI325X memory vs Rubin", expression="256 / 128", unit="GB")
    self_div = MetricRequest(label="AMD revenue growth", expression="12.8 / 12.8 - 40 / 100",
                             unit="billion USD")
    good_ratio = MetricRequest(label="Memory ratio", expression="256 / 128", unit="x")
    good_sum = MetricRequest(label="Combined revenue", expression="18.4 + 4.1", unit="billion USD")
    assert "ratio" in is_well_formed(ratio_in_gb)[1]
    assert "itself" in is_well_formed(self_div)[1]
    assert is_well_formed(good_ratio)[0] and is_well_formed(good_sum)[0]


def test_share_only_for_additive_metrics_ratio_for_specs():
    """Live run produced 'AMD share of combined memory capacity' - meaningless."""
    from app.metrics import Figure, derive_metrics
    from app.tools.calculator import safe_eval
    figs = [Figure(entity="AMD", metric="memory capacity", value=256, unit="GB", source_id=1),
            Figure(entity="NVIDIA", metric="memory capacity", value=128, unit="GB", source_id=2),
            Figure(entity="AMD", metric="revenue", value=5, unit="billion USD", source_id=1),
            Figure(entity="NVIDIA", metric="revenue", value=45, unit="billion USD", source_id=2)]
    got = {m.label: (safe_eval(m.expression), m.unit) for m in derive_metrics(figs)}
    assert got["AMD vs NVIDIA: memory capacity ratio"] == (2.0, "x")
    assert not any("share of combined memory" in k for k in got)
    assert any("share of combined revenue" in k for k in got)


def test_self_division_check_allows_valid_share_formula():
    """Live-run bug: the larger company's share x / (x + y) was wrongly rejected."""
    from app.metrics import is_well_formed
    share = MetricRequest(label="NVIDIA share", expression="193.7 / (193.7 + 7) * 100", unit="%")
    nested = MetricRequest(label="junk", expression="432 - 432 / (432 / 50)", unit="GB")
    assert is_well_formed(share) == (True, "")
    assert not is_well_formed(nested)[0]
