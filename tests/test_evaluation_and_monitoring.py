"""The evaluation harness and monitoring report run end-to-end on real code paths."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate  # noqa: E402
import monitor  # noqa: E402


def test_guard_suites_score_core_cases_correctly():
    g, m = evaluate.suite_grounding(), evaluate.suite_metrics()
    assert g["core"]["precision"] == 1.0 and g["core"]["recall"] == 1.0
    assert m["core"]["precision"] == 1.0 and m["core"]["recall"] == 1.0
    assert m["live_run_cases"]["correct"] == m["live_run_cases"]["n"]


def test_fault_scenario_is_labelled_and_detected(tmp_path, monkeypatch):
    from dataclasses import replace
    from app.config import Settings
    from app.tools.fault_injection import FailureMode

    monkeypatch.setattr(evaluate, "OUT", tmp_path)
    settings = replace(Settings.from_env(load_env_file=False), llm_provider="none")
    sc = {"id": "t", "goal": evaluate.GOALS[0], "injection": ("web_search", FailureMode.MALFORMED, 1)}
    row = evaluate.run_scenario(sc, settings, {})
    faulty = [c for c in row["calls"] if c["truth_faulty"]]
    assert len(faulty) == 1 and faulty[0]["agent_flagged"]
    assert row["recovered"] and row["crashed"] is None


def test_monitor_aggregates_saved_runs(tmp_path):
    run = tmp_path / "runs" / "20260101-000000_x"
    run.mkdir(parents=True)
    report = {"goal": "g", "status": "completed", "tasks_completed": 1, "tasks_total": 1,
              "failures": 1, "recoveries": 1, "sources_analyzed": 1, "duration_s": 10.0,
              "metrics": [], "llm": "none", "planner": "template",
              "events": [{"kind": "recovery"}],
              "tool_calls": [{"tool": "web_search", "success": False, "duration_ms": 5},
                             {"tool": "web_search", "success": True, "duration_ms": 7}]}
    (run / "report.json").write_text(json.dumps(report))
    (run / "trace.jsonl").write_text(json.dumps(
        {"tag": "LLM", "message": "m answered in 2.0s (10 chars) - You are the planning module"}) + "\n")
    assert monitor.main(["--runs-dir", str(tmp_path / "runs"), "--out", str(tmp_path / "m")]) == 0
    s = json.loads((tmp_path / "m" / "monitoring_summary.json").read_text())
    assert s["tools"]["web_search"]["success_rate"] == 0.5
    assert s["llm"]["plan"]["calls"] == 1
    assert (tmp_path / "m" / "dashboard.html").exists()
