"""CLI entry point.

Examples:
    python main.py "Analyze the competitive landscape of NVIDIA in the AI accelerator market"
    python main.py --offline "Analyze the competitive landscape of Voltaic Semiconductors in the AI accelerator market"
    python main.py --offline --inject-failure web_search:malformed "Compare Voltaic Semiconductors and Nimbus Compute in AI accelerators"
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from app.agent import build_agent, run_dir_for
from app.config import Settings
from app.llm import LLMError, build_llm, extract_json
from app.planner import PlanningError
from app.tools.fault_injection import FailureMode, parse_injection
from app.tracing import Tracer


class _Tee:
    """Write console output to stdout and a transcript file at the same time."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for s in self.streams:
            s.write(data)
        return len(data)

    def flush(self) -> None:
        for s in self.streams:
            s.flush()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    modes = ", ".join(m.value for m in FailureMode)
    p = argparse.ArgumentParser(description="Competitive Intelligence Agent")
    p.add_argument("goal", nargs="?", help="natural-language goal (prompted if omitted)")
    p.add_argument("--offline", action="store_true",
                   help="use the bundled FICTIONAL synthetic corpus instead of the web (no keys needed)")
    p.add_argument("--no-llm", action="store_true", help="force deterministic planner/synthesizer")
    p.add_argument("--inject-failure", action="append", default=[], metavar="TOOL:MODE[:N]",
                   help=f"deliberately corrupt the next N calls of a tool. Modes: {modes}")
    p.add_argument("--output-dir", default="runs", help="where run folders are written")
    p.add_argument("--transcript", help="also write the console transcript to this file")
    p.add_argument("--show-report", action="store_true", help="print the Markdown report at the end")
    p.add_argument("-v", "--verbose", action="store_true", help="timestamps in log lines")
    p.add_argument("--check-llm", action="store_true",
                   help="test the configured LLM (e.g. local Ollama/Qwen) and exit")
    return p.parse_args(argv)


def check_llm(settings: Settings) -> int:
    """Quick connectivity + JSON round-trip test for the configured LLM."""
    print(f"LLM provider: {settings.llm_provider} | model: {settings.llm_model} | "
          f"url: {settings.llm_base_url or 'default'} | timeout: {settings.llm_timeout_s:.0f}s")
    llm = build_llm(settings)
    if llm is not None:
        print(f"Using: {llm.name}")
    if llm is None:
        print("No LLM configured. For Ollama set OLLAMA_MODEL=<tag from `ollama list`> in .env")
        return 1
    check = getattr(llm, "check", None)
    if callable(check):
        ok, msg = check()
        print(msg)
        if not ok:
            return 1
    start = time.perf_counter()
    try:
        reply = llm.complete('Reply with exactly this JSON object: {"ok": true}', "ping", 64)
        data = extract_json(reply)
    except LLMError as e:
        print(f"LLM call failed: {e}")
        return 1
    print(f"LLM replied with valid JSON {data} in {time.perf_counter() - start:.1f}s - ready.")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = parse_args(argv)
    if args.check_llm:
        return check_llm(Settings.from_env())
    goal = args.goal or input("Enter your research goal: ").strip()
    if not goal:
        print("A goal is required.", file=sys.stderr)
        return 2
    try:
        injections = [parse_injection(s) for s in args.inject_failure]
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    settings = Settings.from_env()
    run_dir = run_dir_for(goal, Path(args.output_dir))
    run_dir.mkdir(parents=True, exist_ok=True)

    transcript = open(args.transcript, "w", encoding="utf-8") if args.transcript else None
    console = _Tee(sys.stdout, transcript) if transcript else sys.stdout
    tracer = Tracer(stream=console, jsonl_path=run_dir / "trace.jsonl",
                    secrets=settings.secrets(), verbose=args.verbose)
    try:
        agent = build_agent(settings, tracer, offline=args.offline, use_llm=not args.no_llm,
                            injections=injections)
        result = agent.run(goal, output_dir=run_dir)
        if args.show_report:
            console.write("\n" + result.markdown + "\n")
        return 0 if result.report.status != "failed" else 1
    except PlanningError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        tracer.close()
        if transcript:
            transcript.close()


if __name__ == "__main__":
    sys.exit(main())
