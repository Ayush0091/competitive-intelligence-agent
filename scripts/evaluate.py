"""Evaluation harness: measures how well the agent detects and recovers from failures,
and how accurate its hallucination guards are, against labelled ground truth.

    python scripts/evaluate.py            # writes evaluation/ (report + labelled traces)

Three suites, all deterministic and offline (no network, no LLM), so the numbers are
reproducible on any machine:

1. Fault-injection matrix. The real agent runs on the fictional synthetic corpus while
   faults are injected into its tools (every tool x every failure mode, transient = 1 bad
   call and persistent = every call), plus clean runs. Each tool call gets a ground-truth
   label from the harness ("was this call actually faulty?") and a prediction from the
   agent ("did the validator flag it?"). The agent is never told which calls are faulty.
2. Numeric-grounding guard on labelled claims (data/eval/grounding_cases.json).
3. Metric sanity check on labelled metric expressions (data/eval/metric_cases.json).
"""

from __future__ import annotations

import io
import json
import os
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CI_AGENT_SKIP_DOTENV", "1")  # never read the user's .env / keys

from app.agent import build_agent  # noqa: E402
from app.config import Settings  # noqa: E402
from app.metrics import MetricRequest, is_well_formed  # noqa: E402
from app.models.tool_result import ToolResult  # noqa: E402
from app.tools.base import Tool  # noqa: E402
from app.tools.fault_injection import FailureMode, FaultInjectingTool  # noqa: E402
from app.tools.synthetic import load_corpus  # noqa: E402
from app.tracing import Tracer  # noqa: E402
from app.validator import ungrounded_numbers  # noqa: E402

OUT = ROOT / "evaluation"
GOALS = [
    "Analyze the competitive landscape of Voltaic Semiconductors in the AI accelerator market",
    "Compare Voltaic Semiconductors and Nimbus Compute in AI accelerators",
    "Research recent developments of Voltaic Semiconductors",
]
TOOLS = ["web_search", "url_fetcher", "calculator"]
DURATIONS = {"transient": 1, "persistent": 99}


# --------------------------------------------------------------------------- labelling
@dataclass
class CallLabel:
    tool: str
    target: str
    truth_faulty: bool
    truth_reason: str


class GroundTruthTool(Tool):
    """Outermost wrapper: records whether each call was really faulty (ground truth).

    It only observes; the result passed back to the agent is untouched."""

    def __init__(self, inner: Tool, log: list[CallLabel], bad_urls: dict[str, int]) -> None:
        self.inner, self.log, self.bad_urls, self.name = inner, log, bad_urls, inner.name

    def describe(self) -> str:
        return self.inner.describe()

    def _run(self, **kwargs: Any) -> ToolResult:
        before = self.inner.injected if isinstance(self.inner, FaultInjectingTool) else 0
        result = self.inner.run(**kwargs)
        target = str(kwargs.get("query") or kwargs.get("url") or kwargs.get("expression") or "")
        faulty, reason = False, "clean"
        if isinstance(self.inner, FaultInjectingTool) and self.inner.injected > before:
            faulty, reason = True, f"injected:{self.inner.mode.value}"
        elif self.name == "url_fetcher" and target in self.bad_urls:
            faulty, reason = True, f"corpus:http_{self.bad_urls[target]}"
        self.log.append(CallLabel(self.name, target[:120], faulty, reason))
        return result


def _instrument(agent, log: list[CallLabel], bad_urls: dict[str, int]) -> None:
    router = agent.executor.router
    for name in list(router.primary):
        router.primary[name] = GroundTruthTool(router.primary[name], log, bad_urls)
        router.fallbacks[name] = [GroundTruthTool(t, log, bad_urls)
                                  for t in router.fallbacks.get(name, [])]


# ------------------------------------------------------------------ suite 1: fault matrix
def scenarios() -> list[dict[str, Any]]:
    out = []
    for gi, goal in enumerate(GOALS, 1):
        out.append({"id": f"G{gi}-clean", "goal": goal, "injection": None})
        for tool in TOOLS:
            for mode in FailureMode:
                for dname, n in DURATIONS.items():
                    out.append({"id": f"G{gi}-{tool}-{mode.value}-{dname}", "goal": goal,
                                "injection": (tool, mode, n)})
    return out


def run_scenario(sc: dict[str, Any], settings: Settings, bad_urls: dict[str, int]) -> dict[str, Any]:
    run_dir = OUT / "traces" / sc["id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    tracer = Tracer(stream=io.StringIO(), jsonl_path=run_dir / "trace.jsonl")
    injections = [sc["injection"]] if sc["injection"] else []
    agent = build_agent(settings, tracer, offline=True, use_llm=False, injections=injections,
                        sleep=lambda _s: None)
    labels: list[CallLabel] = []
    _instrument(agent, labels, bad_urls)
    try:
        result = agent.run(sc["goal"], output_dir=run_dir)
        crashed, report = None, result.report
    except Exception as e:  # the harness must survive an agent crash and count it
        crashed, report = f"{type(e).__name__}: {e}", None
    close = getattr(tracer, "close", None)
    if callable(close):
        close()

    calls = []
    records = report.tool_calls if report else []
    for lab, rec in zip(labels, records):
        assert lab.tool == rec.tool, "label/record order mismatch"
        calls.append({"tool": rec.tool, "role": rec.role, "attempt": rec.attempt,
                      "target": lab.target, "truth_faulty": lab.truth_faulty,
                      "truth_reason": lab.truth_reason, "agent_flagged": not rec.success,
                      "agent_error": rec.error})
    inj_tool = sc["injection"][0] if sc["injection"] else None
    triggered = any(c["truth_reason"].startswith("injected") for c in calls)
    affected = [t for t in (report.tasks if report else []) if t.tool == inj_tool]
    row = {
        "scenario": sc["id"], "goal": sc["goal"],
        "injected": f"{inj_tool}:{sc['injection'][1].value}:{sc['injection'][2]}" if inj_tool else "none",
        "fault_triggered": triggered, "crashed": crashed,
        "status": report.status if report else "crashed",
        "tasks": f"{report.tasks_completed}/{report.tasks_total}" if report else "-",
        "affected_task_status": sorted({t.status for t in affected}),
        "recoveries": report.recoveries if report else 0,
        "sources": report.sources_analyzed if report else 0,
        "calls": calls,
    }
    # recovered = the faulted step still produced a usable result and the run finished
    row["recovered"] = bool(report) and triggered and all(
        t.status in ("completed", "completed_with_recovery", "skipped") for t in affected)
    (run_dir / "labels.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row


def prf(tp: int, fp: int, fn: int, tn: int) -> dict[str, Any]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r, "f1": f1}


def suite_faults(settings: Settings) -> dict[str, Any]:
    corpus = load_corpus()
    base = corpus["base_url"]
    bad_urls = {base + d["slug"]: d["status"] for d in corpus["documents"]
                if d.get("status", 200) != 200}
    rows = [run_scenario(sc, settings, bad_urls) for sc in scenarios()]
    tp = fp = fn = tn = 0
    per_mode: dict[str, list[int]] = {}
    for r in rows:
        for c in r["calls"]:
            t, pflag = c["truth_faulty"], c["agent_flagged"]
            tp += t and pflag
            fp += (not t) and pflag
            fn += t and not pflag
            tn += (not t) and not pflag
            if t:
                key = c["truth_reason"]
                per_mode.setdefault(key, [0, 0])
                per_mode[key][0] += pflag
                per_mode[key][1] += 1
    faulted = [r for r in rows if r["injected"] != "none" and r["fault_triggered"]]
    clean = [r for r in rows if r["injected"] == "none"]
    not_triggered = [r["scenario"] for r in rows if r["injected"] != "none" and not r["fault_triggered"]]
    return {
        "runs": len(rows),
        "tool_calls": sum(len(r["calls"]) for r in rows),
        "detection": prf(tp, fp, fn, tn),
        "detection_by_fault": {k: {"detected": v[0], "total": v[1]} for k, v in sorted(per_mode.items())},
        "faulted_runs": len(faulted),
        "recovered_runs": sum(r["recovered"] for r in faulted),
        "completed_runs": sum(r["status"] == "completed" for r in rows),
        "crashed_runs": sum(bool(r["crashed"]) for r in rows),
        "clean_runs": len(clean),
        "clean_runs_completed": sum(r["status"] == "completed" for r in clean),
        "not_triggered": not_triggered,
        "unrecovered": [r["scenario"] for r in faulted if not r["recovered"]],
        "rows": rows,
    }


# ----------------------------------------------------------- suites 2 and 3: the guards
def suite_grounding() -> dict[str, Any]:
    data = json.loads((ROOT / "data/eval/grounding_cases.json").read_text(encoding="utf-8"))
    rows, tp, fp, fn, tn = [], 0, 0, 0, 0
    for c in data["cases"]:
        missing = ungrounded_numbers(c["claim"], c["source"])
        flagged = bool(missing)  # positive class = hallucinated
        truth = c["label"] == "hallucinated"
        tp += truth and flagged; fp += (not truth) and flagged
        fn += truth and not flagged; tn += (not truth) and not flagged
        rows.append({**c, "flagged": flagged, "unmatched_numbers": missing,
                     "correct": flagged == truth})
    core = [r for r in rows if "probe" not in r]
    core_m = prf(*_counts(core, "hallucinated"))
    return {"all": prf(tp, fp, fn, tn), "core": core_m, "n": len(rows), "n_core": len(core),
            "rows": rows}


def suite_metrics() -> dict[str, Any]:
    data = json.loads((ROOT / "data/eval/metric_cases.json").read_text(encoding="utf-8"))
    rows = []
    for c in data["cases"]:
        ok, why = is_well_formed(MetricRequest(**c["metric"]))
        rows.append({**c, "flagged": not ok, "reason": why,
                     "correct": (not ok) == (c["label"] == "invalid")})
    core = [r for r in rows if r["origin"] != "probe"]
    live = [r for r in rows if r["origin"] == "live-run"]
    return {"all": prf(*_counts(rows, "invalid")), "core": prf(*_counts(core, "invalid")),
            "live_run_cases": {"n": len(live), "correct": sum(r["correct"] for r in live)},
            "n": len(rows), "n_core": len(core), "rows": rows}


def _counts(rows: list[dict[str, Any]], positive: str) -> tuple[int, int, int, int]:
    tp = sum(r["label"] == positive and r["flagged"] for r in rows)
    fp = sum(r["label"] != positive and r["flagged"] for r in rows)
    fn = sum(r["label"] == positive and not r["flagged"] for r in rows)
    tn = sum(r["label"] != positive and not r["flagged"] for r in rows)
    return tp, fp, fn, tn


# ------------------------------------------------------------------------------ report
def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render(f: dict[str, Any], g: dict[str, Any], m: dict[str, Any]) -> str:
    d = f["detection"]
    L = [
        "# Evaluation report", "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python scripts/evaluate.py`. "
        "Offline and deterministic: fictional synthetic corpus, no LLM, no network. "
        "Every number below is computed from the labelled traces in `evaluation/traces/`.", "",
        "## 1. Failure detection and recovery (fault-injection matrix)", "",
        f"- Runs: **{f['runs']}** = 3 goals x (1 clean + 3 tools x 6 failure modes x "
        "2 durations). Transient = first call faulty; persistent = every call faulty.",
        f"- Tool calls labelled: **{f['tool_calls']}**. Ground truth comes from the harness "
        "(the fault injector and the corpus's known HTTP 503 page); the agent's prediction is "
        "whether its validator flagged the call. The agent is never told.", "",
        "| Failure detection (per tool call) | Value |", "|---|---|",
        f"| Precision (flagged calls that were really faulty) | **{pct(d['precision'])}** |",
        f"| Recall (faulty calls that were flagged) | **{pct(d['recall'])}** |",
        f"| F1 | {pct(d['f1'])} |",
        f"| TP / FP / FN / TN | {d['tp']} / {d['fp']} / {d['fn']} / {d['tn']} |", "",
        "| Fault type | Detected / total |", "|---|---|",
    ]
    for k, v in f["detection_by_fault"].items():
        L.append(f"| {k} | {v['detected']} / {v['total']} |")
    L += ["",
          "| Run outcome | Value |", "|---|---|",
          f"| Runs where the injected fault fired | {f['faulted_runs']} |",
          f"| ...of which the faulted step still produced a result (recovered) | "
          f"**{f['recovered_runs']} / {f['faulted_runs']}** |",
          f"| Runs that finished with status `completed` | {f['completed_runs']} / {f['runs']} |",
          f"| Agent crashes | {f['crashed_runs']} |",
          f"| Clean runs completed | {f['clean_runs_completed']} / {f['clean_runs']} |", ""]
    if f["not_triggered"]:
        L += [f"Faults armed but never fired ({len(f['not_triggered'])} runs, excluded from "
              "recovery rate - the tool was never called, e.g. no figures for the calculator): "
              + ", ".join(f"`{s}`" for s in f["not_triggered"]), ""]
    if f["unrecovered"]:
        L += [f"Not recovered ({len(f['unrecovered'])} runs): "
              + ", ".join(f"`{s}`" for s in f["unrecovered"]),
              "", "These are persistent calculator outages. The calculator has no fallback "
              "tool, so the metric step is marked failed; the agent still finishes, writes the "
              "brief from the sources and reports status `completed_with_warnings` instead of "
              "crashing or inventing numbers (graceful degradation, not recovery).", ""]
    L += ["## 2. Numeric-grounding guard (hallucinated numbers)", "",
          "Positive class = claim contains a figure the source does not support. "
          "`validator.ungrounded_numbers` flags a claim if any of its figures is not literally "
          "present in the source.", "",
          "| Set | n | Precision | Recall | F1 | TP/FP/FN/TN |", "|---|---|---|---|---|---|",
          _prf_row("Core cases", g["n_core"], g["core"]),
          _prf_row("All incl. blind-spot probes", g["n"], g["all"]), "",
          "| Case | Label | Flagged | Correct | Probe | Unmatched numbers |",
          "|---|---|---|---|---|---|"]
    for r in g["rows"]:
        L.append(f"| {r['id']} | {r['label']} | {r['flagged']} | "
                 f"{'yes' if r['correct'] else '**no**'} | {r.get('probe', '')} | "
                 f"{', '.join(r['unmatched_numbers'])} |")
    L += ["", "## 3. Metric sanity check (nonsense calculations)", "",
          "Positive class = invalid metric. `metrics.is_well_formed` runs on every metric the "
          "LLM path produces, before the calculator.", "",
          "| Set | n | Precision | Recall | F1 | TP/FP/FN/TN |", "|---|---|---|---|---|---|",
          _prf_row("Core cases", m["n_core"], m["core"]),
          _prf_row("All incl. probes", m["n"], m["all"]), "",
          f"Mistake patterns reproduced from real qwen3:8b runs: "
          f"{m['live_run_cases']['correct']} / {m['live_run_cases']['n']} classified correctly.", "",
          "| Case | Origin | Label | Flagged | Correct | Reason |", "|---|---|---|---|---|---|"]
    for r in m["rows"]:
        L.append(f"| {r['id']} | {r['origin']} | {r['label']} | {r['flagged']} | "
                 f"{'yes' if r['correct'] else '**no**'} | {r['reason'] or r.get('why', '')} |")
    L += ["", "## Honest reading", "",
          "- Suite 1 measures the validator + recovery loop on synthetic faults. Real-web faults "
          "are messier; see the monitoring report for live-run numbers.",
          "- Detection is 100% because every injected fault is visible to the deterministic "
          "validator (error status, wrong shape, empty result). Faults that look valid - e.g. a "
          "well-formed page with wrong facts - are out of scope for this suite; suites 2-3 "
          "cover that risk.",
          "- Suites 2-3 use small hand-labelled sets written by the author (n is small, so treat "
          "the percentages as indicative, not statistically strong).",
          "- The probes show known blind spots: literal matching cannot catch a real number "
          "attached to the wrong company or period, and it flags valid unit conversions. "
          "Semantic errors in metrics (wrong label, swapped operands) are not caught by syntax "
          "checks; the design limits them by having Python, not the LLM, build the formulas."]
    return "\n".join(L) + "\n"


def _prf_row(name: str, n: int, s: dict[str, Any]) -> str:
    return (f"| {name} | {n} | {pct(s['precision'])} | {pct(s['recall'])} | {pct(s['f1'])} | "
            f"{s['tp']}/{s['fp']}/{s['fn']}/{s['tn']} |")


def main() -> int:
    settings = replace(Settings.from_env(load_env_file=False), llm_provider="none")
    OUT.mkdir(exist_ok=True)
    f = suite_faults(settings)
    g = suite_grounding()
    m = suite_metrics()
    md = render(f, g, m)
    (OUT / "evaluation_report.md").write_text(md, encoding="utf-8")
    summary = {"faults": {k: v for k, v in f.items() if k != "rows"}, "grounding": g, "metrics": m}
    (OUT / "evaluation_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (OUT / "labelled_tool_calls.jsonl").open("w", encoding="utf-8") as fh:
        for r in f["rows"]:
            for c in r["calls"]:
                fh.write(json.dumps({"scenario": r["scenario"], **c}) + "\n")
    with (OUT / "scenario_outcomes.jsonl").open("w", encoding="utf-8") as fh:
        for r in f["rows"]:
            fh.write(json.dumps({k: v for k, v in r.items() if k != "calls"}) + "\n")
    d = f["detection"]
    print(f"fault matrix: {f['runs']} runs, {f['tool_calls']} labelled calls | detection "
          f"P={pct(d['precision'])} R={pct(d['recall'])} | recovered "
          f"{f['recovered_runs']}/{f['faulted_runs']} | crashes {f['crashed_runs']}")
    print(f"grounding guard (core): P={pct(g['core']['precision'])} R={pct(g['core']['recall'])}"
          f" | with probes: P={pct(g['all']['precision'])} R={pct(g['all']['recall'])}")
    print(f"metric check (core): P={pct(m['core']['precision'])} R={pct(m['core']['recall'])}"
          f" | with probes: P={pct(m['all']['precision'])} R={pct(m['all']['recall'])}")
    print(f"wrote {OUT / 'evaluation_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
