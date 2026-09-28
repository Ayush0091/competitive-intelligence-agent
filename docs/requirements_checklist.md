# Requirement → Implementation checklist

The status column records what was actually verified. "Verified" means it was exercised by the test suite (128 passing tests) and/or by the committed runs.

| # | Assignment requirement | Implementation | Evidence / file | Status |
|---|---|---|---|---|
| 1a | Accept a high-level goal | CLI positional argument or interactive prompt | `main.py` | Verified |
| 1b | Decompose the goal into steps on its own | `interpret_goal` → `Objective`; `LLMPlanner` / `TemplatePlanner` → typed `Plan` with dependencies | `app/planner.py`, `app/models/plan.py`, `tests/test_planner.py` | Verified (the LLM path only with a scripted LLM) |
| — | LLM "brain" | Local **Qwen via Ollama** (`OllamaClient`: JSON mode, auto-detect, health check, `--check-llm`). Hosted APIs are optional | `app/llm.py`, `tests/test_ollama_and_replan.py` | Verified with mocks and live on the target PC (qwen3:8b) |
| — | Reasoning-level self-correction | LLM re-planner proposes a new query after a search fails all tool-level recovery; the proposal is validated | `app/replanner.py`, `app/executor.py` | Verified with a scripted LLM |
| 1c | ≥2 distinct tools | `web_search`, `url_fetcher`, `calculator` behind a shared `Tool` interface + router | `app/tools/`, `tests/test_tools.py` | Verified |
| 1d | Self-correct on failure or unexpected result | Validator + `RecoveryManager` (retry → fallbacks → graceful failure); LLM plan corrective retry; citation and metric grounding | `app/validator.py`, `app/recovery.py`, `tests/test_recovery.py` | Verified |
| 1e | Structured final output explaining what the agent did and why | `RunReport` JSON + Markdown with an execution summary, tool calls and events | `app/reporter.py`, `tests/test_report.py` | Verified |
| 2 | No dataset provided; data live or synthetic, documented | Live: keyless DuckDuckGo/Bing search (Tavily optional) + fetcher. Offline: fictional corpus with a notice in the file, the report banner, the README and the transcripts | `app/tools/web_search.py`, `data/synthetic_corpus.json` | Verified live on the target PC (20 runs, see `monitoring/`) and with mocks |
| 3.1 | Natural-language input (CLI) | argparse CLI | `main.py` | Verified |
| 3.2 | Visible planning trace before acting | `render_plan` block printed before execution; no hidden chain-of-thought is exposed | `app/planner.py`, `examples/*.md` | Verified |
| 3.3 | Step-by-step execution with tool calls | `TaskExecutor` runs tasks sequentially with `[TASK]/[TOOL]/[VALIDATION]/[RESULT]` logs | `app/executor.py` | Verified |
| 3.4 | ≥1 deliberately induced failure handled | `--inject-failure tool:mode[:n]` (malformed, empty, timeout, http_error, bad_json, crash) | `app/tools/fault_injection.py`, `examples/run_03_failure_recovery.md` | Verified |
| 3.5 | Final structured result (JSON/Markdown) | `report.json`, `report.md`, `trace.jsonl` per run | `app/agent.py` (`save_outputs`) | Verified |
| 4 | Source code + working README | Setup / run / test commands, env vars, limitations | `README.md`, `requirements.txt`, `.env.example` | A clean install in a fresh venv was verified |
| 4 | Architecture diagram | PNG + SVG + ASCII + Mermaid | `docs/architecture.png`, `docs/architecture.md` | Done |
| 4 | 2–3 sample transcripts | 3 transcripts of verbatim program output (offline mode) | `examples/run_01..03*.md`, `scripts/make_examples.py` | Done: 3 offline + 3 live transcripts (`examples/live_run_0*.md`) |
| 4 | 1-page write-up | Design decisions, limitations, what I'd do next | `docs/design.md` | Done |
| — | Timeout / malformed JSON / HTTP / missing-field / empty-result handling | `classify_http_error`, provider parsing, validator | `tests/test_tools.py`, `tests/test_recovery.py` | Verified |
| — | Safe calculator (no `eval`) | AST whitelist, exponent/length caps, finite check | `app/tools/calculator.py` | Verified |
| — | API keys only from env vars, never logged | `Settings.from_env`, tracer redaction, `.env` in `.gitignore` | `app/config.py`, `app/tracing.py` | Verified |
| — | Do not invent sources or facts | Citation enforcement, metric-number grounding, facts vs *Analysis* labelling | `app/validator.py`, `app/metrics.py` | Verified with a scripted LLM |

## Verified end-to-end on the real target machine

- Windows PC, Python venv, **qwen3:8b via Ollama**, keyless DuckDuckGo/Bing search. Launched with `run_live.bat`.
- `pytest`: all tests passed on that machine (121 at the time; 128 now, all passing in the build sandbox).
- 3 live runs: `examples/live_run_01_normal.md`, `live_run_02_comparison.md`, `live_run_03_failure_recovery.md`. All exited 0 with 6/6 tasks. Run 3 recovered from the injected malformed search response (by retry) and the injected fetch timeouts (by snippet fallback), plus a real HTTP 403.
- The live runs surfaced 7+ real problems. All are fixed and regression-tested; see README → "Lessons from live runs".

## Evaluation and monitoring

- `scripts/evaluate.py`: labelled fault-injection matrix + guard precision/recall → `evaluation/`.
- `scripts/monitor.py`: health metrics, alerts and dashboard from saved runs → `monitoring/`.

## Still missing / limitations

1. **Qwen 8B speed.** On this hardware each LLM call takes about 1–3 minutes, so a full run takes about 6 minutes. A smaller model or a better GPU speeds it up; a larger model improves the analysis.
2. **Keyless search scrapes public pages.** If DuckDuckGo shows a bot check, the agent falls back to Bing automatically. Adding a Tavily key makes search more robust.
3. **Re-planning covers search tasks only.**
