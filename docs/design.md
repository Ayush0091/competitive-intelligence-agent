# Design Write-up (1 page)

**Domain.** I chose competitive intelligence (Appendix A: *"Given a company name, produce a short competitive-landscape brief using public web data"*). It needs real decomposition: find competitors, read the sources, pull out the numbers, compare them and write it up. It also depends on unreliable external data, which makes it a natural test of robustness.

**Architecture: a plan-then-execute pipeline, not a free-running ReAct loop.** The planner produces a typed `Plan` (validated by Pydantic: sequential ids, dependencies only on earlier tasks, a fetch must depend on a search, the plan ends in `synthesize`). The plan is printed, then run in order. I picked this over an open-ended "think → act" loop for three reasons:
- The plan is legible *before* acting, which the assignment asks for.
- Every step is testable in isolation.
- Failure handling can be deterministic instead of hoping the LLM notices an error.

Adaptivity still exists where it matters. Fetch targets come from search results, calculator expressions come from the fetched text, and recovery chooses fallbacks at run time.

**Split of responsibility.** The brain is a **local Qwen model served by Ollama**: free, private, no API key. It interprets the goal, plans, **re-plans failed searches**, extracts labelled figures from sources and writes the synthesis. I call Ollama's native API in JSON mode, which constrains decoding to valid JSON; that is important for 7B–14B models. Python executes the tools, validates, retries, keeps state, does the arithmetic and logs. The LLM is optional, and every LLM step has a deterministic fallback (template planner, regex metric extraction, extractive synthesis). So the agent runs, and the tests pass, with no keys. *Tradeoff:* the no-LLM report is extractive and its competitor list is heuristic.

**Tool selection.**
- `web_search` sits behind a `SearchProvider` interface. The default chain needs no account or key: DuckDuckGo → Bing web RSS → Bing news RSS. Tavily is used first when a key is set, and a synthetic provider is used offline. I first used Wikipedia as the keyless option, but the live run showed Wikimedia now rejects anonymous clients (403), so it became opt-in.
- `url_fetcher` gets full-text evidence.
- `calculator` makes numeric comparisons deterministic. The live runs confirmed that LLM arithmetic is not trustworthy: qwen3:8b wrote expressions like `432 - 432/(432/50)`. So the model now only extracts figures, and Python derives growth, CAGR and share from them.

LLM access uses raw `httpx` rather than vendor SDKs, so providers are easy to swap and to mock.

**Failure handling.**
- Tools **never raise**. Everything becomes a `ToolResult` with a typed, `retryable` error.
- The `RecoveryManager` applies one policy everywhere:
  1. **retry with backoff** (only for retryable errors: timeouts, 5xx and 429 yes; 404 and invalid input no; an empty search skips the identical retry),
  2. **ordered fallbacks** (secondary provider, then a simplified query; for pages, the search snippet),
  3. **LLM re-plan**: for searches, the model sees the failed queries and errors and proposes a different query, which is validated and must not repeat one that already failed,
  4. **graceful failure**: the task is marked failed and the run continues. With zero sources the report honestly says `failed`.
- Deliberate failures are injected with a `FaultInjectingTool` wrapper (`--inject-failure web_search:malformed`). The validator is *not* told a fault was injected, so detection is genuine, and the tests assert on the real retry and fallback path.

**Validation strategy.** Do not trust anything that crosses a boundary:
- **Tool outputs:** schema, types, emptiness, URL safety (including an SSRF check after redirects), minimum text length, finite numbers.
- **LLM outputs:** plans are validated by Pydantic. Metric expressions must use only numbers that appear literally in the cited source. Report findings may only cite source ids that were actually retrieved; unknown ids are removed and uncited "facts" are relabelled as *inference*.
- **In the report:** Markdown marks sourced facts `[S#]` separately from *Analysis*.

**Evaluation and monitoring.** `scripts/evaluate.py` runs a 111-run fault-injection matrix with per-call ground-truth labels (failure detection P/R 100%, faulted step recovered in 90/108 runs, 0 crashes; the rest are persistent calculator outages with no fallback, which still end with a report) and scores the hallucination guards on hand-labelled cases, including probes that expose their blind spots. `scripts/monitor.py` turns saved runs into health metrics, alerts and a dashboard; on 20 live runs it shows the local LLM is ~98% of runtime.

**Limitations.**
- The `run_0*` transcripts and the evaluation use a clearly labelled **fictional offline corpus** (deterministic, no keys). The `live_run_0*` transcripts use real web data + local Qwen on a Windows PC.
- Keyless search scrapes public HTML/RSS, which is more fragile than an API (bot checks are handled as empty results → fallback).
- A local 8B model takes about 1.5–3 minutes per LLM call on my hardware, so a full run takes about 6 minutes.
- Without an LLM, the competitor detection is heuristic.
- Metrics inherit their sources' definitions and periods.
- Re-planning covers search tasks only.
- The quality of the analysis depends on the local model size.
- Fetching is sequential.

**With more time I would:**
- Extend re-planning to every task type and add a critic loop that checks coverage against the objective.
- Extend the evaluation to many live goals with human-labelled report quality (citation precision, coverage).
- Filter search by recency and score source quality.
- Fetch in parallel with rate limits and caching.
- Add a structured financial-data tool (e.g. SEC EDGAR) so metrics do not depend on figures in news text.
