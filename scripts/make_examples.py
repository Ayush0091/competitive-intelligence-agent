"""Regenerate the sample transcripts in examples/ by actually running the agent.

    python scripts/make_examples.py            # offline, fictional synthetic corpus
    python scripts/make_examples.py --live     # real web + LLM (needs keys in .env)

Every transcript is the verbatim console output of main.py; nothing is hand-edited.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402

OFFLINE_RUNS = [
    ("run_01_normal.md", "Run 1 - Normal competitive landscape analysis", [],
     "Analyze the competitive landscape of Voltaic Semiconductors in the AI accelerator market"),
    ("run_02_comparison.md", "Run 2 - Company comparison", [],
     "Compare Voltaic Semiconductors and Nimbus Compute in AI accelerators"),
    ("run_03_failure_recovery.md", "Run 3 - Deliberately induced failures + recovery",
     ["--inject-failure", "web_search:malformed", "--inject-failure", "url_fetcher:timeout:2"],
     "Research recent developments of Voltaic Semiconductors"),
]
LIVE_RUNS = [
    ("live_run_01_normal.md", "Live run 1 - Normal competitive landscape analysis", [],
     "Analyze the competitive landscape of NVIDIA in the AI accelerator market"),
    ("live_run_02_comparison.md", "Live run 2 - Company comparison", [],
     "Compare NVIDIA and AMD in AI accelerators"),
    ("live_run_03_failure_recovery.md", "Live run 3 - Deliberately induced failures + recovery",
     ["--inject-failure", "web_search:malformed", "--inject-failure", "url_fetcher:timeout:2"],
     "Research recent developments of AMD in AI accelerators"),
]

OFFLINE_NOTE = (
    "> **Data mode: OFFLINE SYNTHETIC.** This run used the bundled fictional corpus "
    "(`data/synthetic_corpus.json`) because it was generated in a sandbox without internet "
    "access or API keys. Company names and figures are invented. Everything else - planner, "
    "tools, HTTP fetching/parsing (via an in-process mock transport), validation, retries, "
    "fallbacks, calculator and report generation - is the real code path. "
    "Regenerate with live data: `python scripts/make_examples.py --live`.")
LIVE_NOTE = "> **Data mode: LIVE.** Real web search/fetch; LLM as configured in `.env`."


def main_cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--only", type=int, choices=[1, 2, 3], help="regenerate just one run")
    args = ap.parse_args()
    runs = LIVE_RUNS if args.live else OFFLINE_RUNS
    if args.only:
        runs = [runs[args.only - 1]]
    out_dir = ROOT / "examples"
    out_dir.mkdir(exist_ok=True)
    for filename, title, extra, goal in runs:
        flags = ([] if args.live else ["--offline"]) + extra + ["--show-report"]
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "t.txt"
            code = main.main(flags + ["--output-dir", str(ROOT / "runs"),
                                      "--transcript", str(transcript), goal])
            text = transcript.read_text(encoding="utf-8")
        command = " ".join(["python", "main.py", *flags, f'"{goal}"'])
        md = (f"# {title}\n\n{LIVE_NOTE if args.live else OFFLINE_NOTE}\n\n"
              f"**Command:**\n\n```bash\n{command}\n```\n\n"
              f"**Exit code:** {code}\n\n**Console transcript (verbatim):**\n\n```text\n{text}```\n")
        (out_dir / filename).write_text(md, encoding="utf-8")
        print(f"wrote examples/{filename} (exit {code})")


if __name__ == "__main__":
    main_cli()
