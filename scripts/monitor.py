"""Monitoring report: aggregates every saved run (runs/*/report.json + trace.jsonl) into
health metrics, alert checks and a self-contained HTML dashboard.

    python scripts/monitor.py                     # reads runs/, writes monitoring/
    python scripts/monitor.py --runs-dir other/   # any folder of run directories

Nothing is sampled or estimated: every figure is counted from the saved files.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Alert thresholds (a production deployment would tune these on real traffic).
THRESHOLDS = {
    "run_success_rate_min": 0.90,     # share of runs with status completed
    "tool_success_rate_min": 0.80,    # per tool, share of calls that passed validation
    "llm_p95_latency_s_max": 120.0,   # per LLM call
    "run_p95_duration_s_max": 600.0,  # end-to-end
    "gave_up_per_run_max": 3.0,       # tool calls abandoned after all recovery
}

_LLM_LINE = re.compile(r"answered in ([\d.]+)s \((\d+) chars\) - (.*)")
_PURPOSES = [("re-planning module", "re-plan"), ("planning module", "plan"),
             ("reporting module", "synthesis (brief)"), ("extract", "figure extraction")]


def _purpose(prompt_head: str) -> str:
    low = prompt_head.lower()
    for key, name in _PURPOSES:
        if key in low:
            return name
    return "other"


def pctl(values: list[float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = max(0, min(len(v) - 1, round(p / 100 * (len(v) - 1))))
    return v[k]


def load_runs(runs_dir: Path) -> list[dict[str, Any]]:
    runs = []
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        rep, tr = d / "report.json", d / "trace.jsonl"
        if not rep.exists():
            continue
        report = json.loads(rep.read_text(encoding="utf-8"))
        trace = ([json.loads(l) for l in tr.read_text(encoding="utf-8").splitlines() if l.strip()]
                 if tr.exists() else [])
        runs.append({"id": d.name, "report": report, "trace": trace})
    return runs


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    tools: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "ok": 0, "lat": [], "r_calls": 0, "r_ok": 0})
    recent_ids = {r["id"] for r in runs[-10:]}
    errors: Counter = Counter()
    providers: Counter = Counter()
    events: Counter = Counter()
    llm_lat: dict[str, list[float]] = defaultdict(list)
    per_run = []
    for r in runs:
        rep, trace = r["report"], r["trace"]
        for c in rep["tool_calls"]:
            t = tools[c["tool"]]
            t["calls"] += 1
            t["ok"] += bool(c["success"])
            if r["id"] in recent_ids:
                t["r_calls"] += 1
                t["r_ok"] += bool(c["success"])
            if c.get("duration_ms") is not None:
                t["lat"].append(c["duration_ms"])
        for e in rep["events"]:
            events[e["kind"]] += 1
        llm_calls = faults = replans = 0
        run_llm_s = 0.0
        for e in trace:
            if "error_type" in e:
                errors[f"{e.get('tool')}: {e['error_type']}"] += 1
            m = e.get("message", "")
            if e.get("tag") == "LLM" and (mm := _LLM_LINE.search(m)):
                llm_lat[_purpose(mm.group(3))].append(float(mm.group(1)))
                llm_calls += 1
                run_llm_s += float(mm.group(1))
            if e.get("tag") == "FAULT":
                faults += 1
            if e.get("tag") == "REPLAN" and m.startswith("New query"):
                replans += 1
            if e.get("tag") == "RESULT" and (pm := re.search(r"provider=([\w-]+)", m)):
                providers[pm.group(1)] += 1
        per_run.append({
            "run": r["id"][:15], "goal": rep["goal"], "status": rep["status"],
            "tasks": f"{rep['tasks_completed']}/{rep['tasks_total']}",
            "tool_calls": len(rep["tool_calls"]), "failures": rep["failures"],
            "recoveries": rep["recoveries"],
            "gave_up": sum(e["kind"] == "gave_up" for e in rep["events"]),
            "sources": rep["sources_analyzed"],
            "metrics": sum(m.get("status") == "ok" for m in rep["metrics"]),
            "duration_s": round(rep["duration_s"], 1), "llm_calls": llm_calls,
            "llm_s": round(run_llm_s, 1), "injected_faults": faults, "replans": replans,
            "llm": rep.get("llm"), "planner": rep.get("planner"),
        })
    durations = [p["duration_s"] for p in per_run]
    tool_rows = {name: {"calls": t["calls"], "success_rate": t["ok"] / t["calls"] if t["calls"] else None,
                        "recent_success_rate": t["r_ok"] / t["r_calls"] if t["r_calls"] else None,
                        "p50_ms": pctl(t["lat"], 50), "p95_ms": pctl(t["lat"], 95)}
                 for name, t in sorted(tools.items())}
    all_llm = [x for v in llm_lat.values() for x in v]
    llm_rows = {k: {"calls": len(v), "p50_s": pctl(v, 50), "p95_s": pctl(v, 95),
                    "mean_s": statistics.mean(v)} for k, v in sorted(llm_lat.items())}
    completed = sum(p["status"] == "completed" for p in per_run)
    summary = {
        "runs": len(per_run), "completed": completed,
        "run_success_rate": completed / len(per_run) if per_run else None,
        "tool_calls": sum(p["tool_calls"] for p in per_run),
        "failures": sum(p["failures"] for p in per_run),
        "recoveries": sum(p["recoveries"] for p in per_run),
        "gave_up": sum(p["gave_up"] for p in per_run),
        "sources": sum(p["sources"] for p in per_run),
        "metrics": sum(p["metrics"] for p in per_run),
        "llm_calls": len(all_llm), "llm_p50_s": pctl(all_llm, 50), "llm_p95_s": pctl(all_llm, 95),
        "run_p50_s": pctl(durations, 50), "run_p95_s": pctl(durations, 95),
        "llm_share_of_runtime": (sum(p["llm_s"] for p in per_run) / sum(durations)) if durations else None,
        "injected_faults": sum(p["injected_faults"] for p in per_run),
    }
    return {"summary": summary, "tools": tool_rows, "llm": llm_rows, "errors": dict(errors.most_common()),
            "providers": dict(providers.most_common()), "events": dict(events.most_common()),
            "per_run": per_run, "alerts": alerts(summary, tool_rows, per_run)}


def alerts(s: dict[str, Any], tools: dict[str, Any], per_run: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []

    def check(name: str, ok: bool, detail: str) -> None:
        out.append({"check": name, "status": "OK" if ok else "ALERT", "detail": detail})

    rate = s["run_success_rate"] or 0
    check("Run success rate", rate >= THRESHOLDS["run_success_rate_min"],
          f"{rate:.0%} (threshold >= {THRESHOLDS['run_success_rate_min']:.0%})")
    recent = per_run[-10:]
    rrate = sum(p["status"] == "completed" for p in recent) / len(recent) if recent else 0
    check("Run success rate, last 10 runs", rrate >= THRESHOLDS["run_success_rate_min"],
          f"{rrate:.0%}")
    for name, t in tools.items():
        sr = t["success_rate"] or 0
        check(f"Tool success rate: {name}", sr >= THRESHOLDS["tool_success_rate_min"],
              f"{sr:.0%} of {t['calls']} calls; last 10 runs {t['recent_success_rate'] or 0:.0%} "
              f"(threshold >= {THRESHOLDS['tool_success_rate_min']:.0%})")
    if s["llm_p95_s"] is not None:
        check("LLM p95 latency", s["llm_p95_s"] <= THRESHOLDS["llm_p95_latency_s_max"],
              f"{s['llm_p95_s']:.1f}s (threshold <= {THRESHOLDS['llm_p95_latency_s_max']:.0f}s)")
    if s["run_p95_s"] is not None:
        check("Run p95 duration", s["run_p95_s"] <= THRESHOLDS["run_p95_duration_s_max"],
              f"{s['run_p95_s']:.0f}s (threshold <= {THRESHOLDS['run_p95_duration_s_max']:.0f}s)")
    gpr = s["gave_up"] / s["runs"] if s["runs"] else 0
    check("Abandoned tool calls per run", gpr <= THRESHOLDS["gave_up_per_run_max"],
          f"{gpr:.1f} (threshold <= {THRESHOLDS['gave_up_per_run_max']:.0f})")
    return out


# ------------------------------------------------------------------------------ output
def _f(x: Any, fmt: str = "{:.1f}") -> str:
    return "-" if x is None else fmt.format(x)


def render_md(a: dict[str, Any]) -> str:
    s = a["summary"]
    L = ["# Monitoring report", "",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python scripts/monitor.py` from "
         f"{s['runs']} saved runs (`runs/*/report.json` + `trace.jsonl`). All figures are counted "
         "from those files.", "",
         "## Health summary", "", "| Metric | Value |", "|---|---|",
         f"| Runs | {s['runs']} ({s['completed']} completed, {s['runs'] - s['completed']} failed) |",
         f"| Run success rate | {_f(s['run_success_rate'], '{:.0%}')} |",
         f"| Tool calls / failures / recoveries / abandoned | {s['tool_calls']} / {s['failures']} / "
         f"{s['recoveries']} / {s['gave_up']} |",
         f"| Sources analysed / metrics computed | {s['sources']} / {s['metrics']} |",
         f"| Deliberately injected faults | {s['injected_faults']} |",
         f"| Run duration p50 / p95 | {_f(s['run_p50_s'], '{:.0f}')}s / {_f(s['run_p95_s'], '{:.0f}')}s |",
         f"| LLM calls, latency p50 / p95 | {s['llm_calls']}, {_f(s['llm_p50_s'])}s / {_f(s['llm_p95_s'])}s |",
         f"| Share of runtime spent waiting on the LLM | {_f(s['llm_share_of_runtime'], '{:.0%}')} |", "",
         "## Alerts", "", "| Check | Status | Detail |", "|---|---|---|"]
    L += [f"| {x['check']} | {'**ALERT**' if x['status'] == 'ALERT' else 'OK'} | {x['detail']} |"
          for x in a["alerts"]]
    L += ["", "## Tools", "", "| Tool | Calls | Success rate | Success, last 10 runs | p50 latency | p95 latency |",
          "|---|---|---|---|---|---|"]
    L += [f"| {n} | {t['calls']} | {_f(t['success_rate'], '{:.0%}')} | "
          f"{_f(t['recent_success_rate'], '{:.0%}')} | {_f(t['p50_ms'], '{:.0f}')} ms | "
          f"{_f(t['p95_ms'], '{:.0f}')} ms |" for n, t in a["tools"].items()]
    L += ["", "## LLM calls by purpose", "", "| Purpose | Calls | p50 | p95 | mean |", "|---|---|---|---|---|"]
    L += [f"| {k} | {v['calls']} | {_f(v['p50_s'])}s | {_f(v['p95_s'])}s | {_f(v['mean_s'])}s |"
          for k, v in a["llm"].items()]
    L += ["", "## Errors by tool and type", "", "| Error | Count |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in a["errors"].items()]
    L += ["", "## Recovery events", "", "| Event kind | Count |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in a["events"].items()]
    L += ["", "## Search providers that returned results", "", "| Provider | Searches |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in a["providers"].items()]
    L += ["", "## Per run", "",
          "| Run | Goal | Status | Tasks | Calls | Fail | Recov | Gave up | Faults | Re-plans | Sources | Metrics | LLM s | Total s |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {p['run']} | {p['goal'][:45]} | {p['status']} | {p['tasks']} | {p['tool_calls']} | "
          f"{p['failures']} | {p['recoveries']} | {p['gave_up']} | {p['injected_faults']} | {p['replans']} | "
          f"{p['sources']} | {p['metrics']} | {p['llm_s']:.0f} | {p['duration_s']:.0f} |" for p in a["per_run"]]
    return "\n".join(L) + "\n"


def _bars(items: list[tuple[str, float]], unit: str = "", width: int = 420, color: str = "var(--accent)",
          fmt: str = "{:.0f}") -> str:
    if not items:
        return "<p class='muted'>No data</p>"
    mx = max(v for _, v in items) or 1
    rows, h = [], 26
    for i, (label, v) in enumerate(items):
        w = max(2, v / mx * (width - 240))
        y = i * h
        rows.append(f"<text x='0' y='{y + 17}' class='lbl'>{html.escape(label[:26])}</text>"
                    f"<rect x='180' y='{y + 5}' width='{w:.1f}' height='16' rx='3' fill='{color}'/>"
                    f"<text x='{186 + w:.1f}' y='{y + 17}' class='val'>{fmt.format(v)}{unit}</text>")
    return f"<svg viewBox='0 0 {width} {len(items) * h}' width='100%' role='img'>{''.join(rows)}</svg>"


def _timeline(per_run: list[dict[str, Any]]) -> str:
    n = len(per_run)
    if not n:
        return ""
    W, H, pad = 860, 200, 30
    mx = max(max(p["duration_s"] for p in per_run), 1)
    bw = (W - 2 * pad) / n
    out = []
    for i, p in enumerate(per_run):
        x = pad + i * bw
        total_h = p["duration_s"] / mx * (H - 50)
        llm_h = min(p["llm_s"], p["duration_s"]) / mx * (H - 50)
        col = "var(--ok)" if p["status"] == "completed" else "var(--bad)"
        out.append(f"<rect x='{x + 3:.1f}' y='{H - 20 - total_h:.1f}' width='{bw - 6:.1f}' "
                   f"height='{total_h:.1f}' fill='{col}' opacity='.35'/>"
                   f"<rect x='{x + 3:.1f}' y='{H - 20 - llm_h:.1f}' width='{bw - 6:.1f}' "
                   f"height='{llm_h:.1f}' fill='{col}'/>"
                   f"<text x='{x + bw / 2:.1f}' y='{H - 5}' class='tick'>{i + 1}</text>")
        if p["failures"]:
            out.append(f"<text x='{x + bw / 2:.1f}' y='{H - 24 - total_h:.1f}' class='tick'>"
                       f"{p['failures']}f</text>")
    return f"<svg viewBox='0 0 {W} {H}' width='100%' role='img'>{''.join(out)}</svg>"


def render_html(a: dict[str, Any]) -> str:
    s = a["summary"]
    alerts_n = sum(x["status"] == "ALERT" for x in a["alerts"])
    kpis = [("Runs", f"{s['runs']}"), ("Success rate", _f(s["run_success_rate"], "{:.0%}")),
            ("Tool calls", f"{s['tool_calls']}"), ("Failures → recovered", f"{s['failures']} → {s['recoveries']}"),
            ("LLM p50 / p95", f"{_f(s['llm_p50_s'], '{:.0f}')}s / {_f(s['llm_p95_s'], '{:.0f}')}s"),
            ("Run p50", f"{_f(s['run_p50_s'], '{:.0f}')}s"), ("Alerts", f"{alerts_n}")]
    kpi_html = "".join(f"<div class='kpi'><div class='k'>{html.escape(k)}</div><div class='v'>{html.escape(v)}</div></div>"
                       for k, v in kpis)
    alert_rows = "".join(
        f"<tr><td>{html.escape(x['check'])}</td><td><span class='pill {'bad' if x['status'] == 'ALERT' else 'good'}'>"
        f"{x['status']}</span></td><td class='wrap'>{html.escape(x['detail'])}</td></tr>" for x in a["alerts"])
    tool_rows = "".join(
        f"<tr><td>{n}</td><td>{t['calls']}</td><td>{_f(t['success_rate'], '{:.0%}')}</td>"
        f"<td>{_f(t['recent_success_rate'], '{:.0%}')}</td>"
        f"<td>{_f(t['p50_ms'], '{:.0f}')} ms</td><td>{_f(t['p95_ms'], '{:.0f}')} ms</td></tr>"
        for n, t in a["tools"].items())
    run_rows = "".join(
        f"<tr><td>{i + 1}</td><td>{p['run']}</td><td>{html.escape(p['goal'][:36])}</td>"
        f"<td><span class='pill {'good' if p['status'] == 'completed' else 'bad'}'>{p['status']}</span></td>"
        f"<td>{p['tasks']}</td><td>{p['failures']}</td><td>{p['recoveries']}</td><td>{p['injected_faults']}</td>"
        f"<td>{p['replans']}</td><td>{p['sources']}</td><td>{p['metrics']}</td><td>{p['duration_s']:.0f}s</td></tr>"
        for i, p in enumerate(a["per_run"]))
    llm_bars = _bars([(f"{k} (n={v['calls']})", v["mean_s"]) for k, v in a["llm"].items()], "s")
    err_bars = _bars(list(a["errors"].items()), color="var(--bad)")
    ev_bars = _bars(list(a["events"].items()), color="var(--accent2)")
    prov_bars = _bars(list(a["providers"].items()), color="var(--accent2)")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent Monitoring Dashboard</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#1c2430;--muted:#687385;--line:#e3e7ee;--accent:#3b6fd8;--accent2:#7a5cc9;--ok:#1f9d63;--bad:#d2493b}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#12151b;--card:#1b2029;--fg:#e6e9ef;--muted:#98a2b3;--line:#2b3240}}}}
:root[data-theme="dark"]{{--bg:#12151b;--card:#1b2029;--fg:#e6e9ef;--muted:#98a2b3;--line:#2b3240}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:20px 16px 40px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:15px;margin:0 0 10px}}
.muted{{color:var(--muted)}}.grid{{display:grid;gap:14px}}.kpis{{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin:16px 0}}
.two{{grid-template-columns:repeat(auto-fit,minmax(460px,1fr))}}.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow-x:auto}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}.kpi .k{{color:var(--muted);font-size:12px}}.kpi .v{{font-size:21px;font-weight:650;margin-top:2px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}}td.wrap{{white-space:normal;min-width:180px}}td{{vertical-align:middle}}th{{color:var(--muted);font-weight:600}}
.pill{{padding:2px 8px;border-radius:99px;font-size:12px;font-weight:600}}.good{{background:color-mix(in srgb,var(--ok) 18%,transparent);color:var(--ok)}}.bad{{background:color-mix(in srgb,var(--bad) 18%,transparent);color:var(--bad)}}
svg .lbl,svg .val,svg .tick{{fill:var(--fg);font-size:12px}}svg .tick{{text-anchor:middle;fill:var(--muted);font-size:11px}}
.legend span{{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px;vertical-align:middle}}
</style></head><body><div class="wrap">
<h1>Competitive Intelligence Agent — Monitoring Dashboard</h1>
<div class="muted">Generated {datetime.now():%Y-%m-%d %H:%M} by <code>scripts/monitor.py</code> from {s['runs']} saved live runs
(local qwen3:8b via Ollama; Tavily / DuckDuckGo search). Every number is counted from <code>runs/*/report.json</code> and <code>trace.jsonl</code>.</div>
<div class="grid kpis">{kpi_html}</div>
<div class="card" style="margin-bottom:14px"><h2>Runs over time — duration (light) and time waiting on the LLM (solid)</h2>
<div class="legend muted"><span style="background:var(--ok)"></span>completed<span style="background:var(--bad)"></span>failed · label = tool failures in the run</div>
{_timeline(a['per_run'])}</div>
<div class="grid two">
<div class="card"><h2>Alert checks</h2><table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>{alert_rows}</table></div>
<div class="card"><h2>Tool health</h2><table><tr><th>Tool</th><th>Calls</th><th>Success</th><th>Last 10</th><th>p50</th><th>p95</th></tr>{tool_rows}</table>
<h2 style="margin-top:14px">Mean LLM latency by purpose</h2>{llm_bars}</div>
<div class="card"><h2>Errors by tool and type</h2>{err_bars}</div>
<div class="card"><h2>Recovery / validation events</h2>{ev_bars}<h2 style="margin-top:14px">Search provider that answered</h2>{prov_bars}</div>
</div>
<div class="card" style="margin-top:14px"><h2>Per-run detail</h2><table>
<tr><th>#</th><th>Run</th><th>Goal</th><th>Status</th><th>Tasks</th><th>Fail</th><th>Recov</th><th>Faults armed</th><th>Re-plans</th><th>Sources</th><th>Metrics</th><th>Duration</th></tr>
{run_rows}</table></div>
</div></body></html>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--out", default=str(ROOT / "monitoring"))
    args = ap.parse_args(argv)
    runs = load_runs(Path(args.runs_dir))
    if not runs:
        print(f"no runs with report.json under {args.runs_dir}", file=sys.stderr)
        return 1
    a = aggregate(runs)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "monitoring_summary.json").write_text(json.dumps(a, indent=2), encoding="utf-8")
    (out / "monitoring_report.md").write_text(render_md(a), encoding="utf-8")
    (out / "dashboard.html").write_text(render_html(a), encoding="utf-8")
    s = a["summary"]
    print(f"{s['runs']} runs | success {s['run_success_rate']:.0%} | {s['tool_calls']} tool calls, "
          f"{s['failures']} failures, {s['recoveries']} recoveries | alerts: "
          f"{sum(x['status'] == 'ALERT' for x in a['alerts'])}")
    print(f"wrote {out / 'dashboard.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
