# Run 3 - Deliberately induced failures + recovery

> **Data mode: OFFLINE SYNTHETIC.** This run used the bundled fictional corpus (`data/synthetic_corpus.json`) because it was generated in a sandbox without internet access or API keys. Company names and figures are invented. Everything else - planner, tools, HTTP fetching/parsing (via an in-process mock transport), validation, retries, fallbacks, calculator and report generation - is the real code path. Regenerate with live data: `python scripts/make_examples.py --live`.

**Command:**

```bash
python main.py --offline --inject-failure web_search:malformed --inject-failure url_fetcher:timeout:2 --show-report "Research recent developments of Voltaic Semiconductors"
```

**Exit code:** 0

**Console transcript (verbatim):**

```text
[AGENT] Goal received: "Research recent developments of Voltaic Semiconductors"
[AGENT] mode=offline_synthetic | llm=none | search=web_search[synthetic]
[FAULT] Deliberate failure armed: web_search -> 'malformed' for the next 1 call(s) (validator is not told)
[FAULT] Deliberate failure armed: url_fetcher -> 'timeout' for the next 2 call(s) (validator is not told)

============================================================
AGENT EXECUTION PLAN
============================================================

Goal:
  Research recent developments of Voltaic Semiconductors

Interpreted objective:
  type=developments  targets=Voltaic Semiconductors  market=n/a

Planner: template (no LLM configured -> deterministic rule-based planner)

Tasks:
  [1] Research recent developments for Voltaic Semiconductors
       -> web_search (query="Voltaic Semiconductors recent developments")
  [2] Find recent announcements and product news for Voltaic Semiconductors
       -> web_search (query="Voltaic Semiconductors announcements news")
  [3] Find competitive context for Voltaic Semiconductors
       -> web_search (query="Voltaic Semiconductors competitors")
  [4] Retrieve and read the most relevant public sources
       -> url_fetcher (inputs from tasks [1, 2, 3])
  [5] Compute comparable metrics from figures stated in sources
       -> calculator (inputs from tasks [4])
  [6] Synthesize validated evidence into the final report
       -> synthesize (inputs from tasks [4, 5])

Tools:
  ✓ Web Search
  ✓ URL Fetcher
  ✓ Calculator

Execution mode:
  Sequential | every tool result validated | recovery enabled (retries=1, fallbacks on)
============================================================

[PLAN] 6 tasks generated; executing sequentially
[TASK 1] Research recent developments for Voltaic Semiconductors
[TOOL] web_search[synthetic] query="Voltaic Semiconductors recent developments" (attempt 1)
[ERROR] invalid tool response: missing "results" [malformed_response]
[RECOVERY] Validation failed. Retry attempt 1/1 in 0.5s...
[TOOL] web_search[synthetic] query="Voltaic Semiconductors recent developments" (attempt 2)
[VALIDATION] passed in 1 ms
[RECOVERY] Recovered via retry (attempt 2/2)
[RESULT] 5 valid results (provider=synthetic)
[RESULT]   - [SYNTHETIC] Voltaic Semiconductors posts record data-center revenue | https://synthetic.example/voltaic-fy2025-results
[RESULT]   - [SYNTHETIC] Voltaic announces sovereign AI data-center partnership with Orbital  | https://synthetic.example/voltaic-orbital-partnership
[RESULT]   - [SYNTHETIC] Nimbus Compute unveils MX3 accelerator to challenge Voltaic | https://synthetic.example/nimbus-mx3-launch
[RESULT]   - [SYNTHETIC] AI accelerator market overview: Voltaic leads, rivals close in | https://synthetic.example/ai-accelerator-market-overview
[RESULT]   - [SYNTHETIC] Voltaic vs Nimbus Compute: benchmark comparison of Arc 4 and MX3 | https://synthetic.example/voltaic-vs-nimbus-benchmarks
[TASK 1] COMPLETED_WITH_RECOVERY - 5 results via retry
[TASK 2] Find recent announcements and product news for Voltaic Semiconductors
[TOOL] web_search[synthetic] query="Voltaic Semiconductors announcements news" (attempt 1)
[VALIDATION] passed in 0 ms
[RESULT] 5 valid results (provider=synthetic)
[RESULT]   - [SYNTHETIC] Voltaic Semiconductors posts record data-center revenue | https://synthetic.example/voltaic-fy2025-results
[RESULT]   - [SYNTHETIC] New export rules restrict advanced accelerator shipments | https://synthetic.example/accelerator-export-rules
[RESULT]   - [SYNTHETIC] Voltaic announces sovereign AI data-center partnership with Orbital  | https://synthetic.example/voltaic-orbital-partnership
[RESULT]   - [SYNTHETIC] AI accelerator market overview: Voltaic leads, rivals close in | https://synthetic.example/ai-accelerator-market-overview
[RESULT]   - [SYNTHETIC] Nimbus Compute unveils MX3 accelerator to challenge Voltaic | https://synthetic.example/nimbus-mx3-launch
[TASK 2] COMPLETED - 5 results via first_try
[TASK 3] Find competitive context for Voltaic Semiconductors
[TOOL] web_search[synthetic] query="Voltaic Semiconductors competitors" (attempt 1)
[VALIDATION] passed in 0 ms
[RESULT] 5 valid results (provider=synthetic)
[RESULT]   - [SYNTHETIC] Voltaic Semiconductors posts record data-center revenue | https://synthetic.example/voltaic-fy2025-results
[RESULT]   - [SYNTHETIC] AI accelerator market overview: Voltaic leads, rivals close in | https://synthetic.example/ai-accelerator-market-overview
[RESULT]   - [SYNTHETIC] Nimbus Compute unveils MX3 accelerator to challenge Voltaic | https://synthetic.example/nimbus-mx3-launch
[RESULT]   - [SYNTHETIC] Voltaic announces sovereign AI data-center partnership with Orbital  | https://synthetic.example/voltaic-orbital-partnership
[RESULT]   - [SYNTHETIC] Helix Silicon raises funding for low-power inference chips | https://synthetic.example/helix-inference-chips
[TASK 3] COMPLETED - 5 results via first_try
[TASK 4] Retrieve and read the most relevant public sources
[VALIDATION] Skipped 2 off-topic search result(s) that mention none of ['semiconductor', 'voltaic']
[TOOL] url_fetcher url="https://synthetic.example/voltaic-fy2025-results" (attempt 1)
[ERROR] request timed out (ReadTimeout) [timeout]
[RECOVERY] Tool call failed. Retry attempt 1/1 in 0.5s...
[TOOL] url_fetcher url="https://synthetic.example/voltaic-fy2025-results" (attempt 2)
[ERROR] request timed out (ReadTimeout) [timeout]
[RECOVERY] Giving up after 2 attempt(s): request timed out (ReadTimeout)
[RECOVERY] Degraded gracefully: using search snippet for S1 instead of full page
[TOOL] url_fetcher url="https://synthetic.example/voltaic-orbital-partnership" (attempt 1)
[VALIDATION] passed in 1 ms
[RESULT] S2: 385 chars extracted
[TOOL] url_fetcher url="https://synthetic.example/ai-accelerator-market-overview" (attempt 1)
[VALIDATION] passed in 1 ms
[RESULT] S3: 599 chars extracted
[TOOL] url_fetcher url="https://synthetic.example/nimbus-mx3-launch" (attempt 1)
[VALIDATION] passed in 1 ms
[RESULT] S4: 678 chars extracted
[TOOL] url_fetcher url="https://synthetic.example/voltaic-vs-nimbus-benchmarks" (attempt 1)
[VALIDATION] passed in 1 ms
[RESULT] S5: 514 chars extracted
[TASK 4] COMPLETED_WITH_RECOVERY - 4 full pages, 1 snippet fallbacks, 0 skipped
[TASK 5] Compute comparable metrics from figures stated in sources
[TOOL] calculator expression="(18.4 - 10.2) / 10.2 * 100" (attempt 1)
[VALIDATION] passed in 0 ms
[RESULT] Voltaic Semiconductors: revenue growth vs prior period = 80.39%
[TOOL] calculator expression="(4.1 - 2.3) / 2.3 * 100" (attempt 1)
[VALIDATION] passed in 0 ms
[RESULT] Nimbus Compute: revenue growth vs prior period = 78.26%
[TOOL] calculator expression="18.4 / (18.4 + 4.1) * 100" (attempt 1)
[VALIDATION] passed in 0 ms
[RESULT] Voltaic Semiconductors: share of combined reported revenue of companies found (not total market share) = 81.78%
[TOOL] calculator expression="4.1 / (18.4 + 4.1) * 100" (attempt 1)
[VALIDATION] passed in 0 ms
[RESULT] Nimbus Compute: share of combined reported revenue of companies found (not total market share) = 18.22%
[TASK 5] COMPLETED - 4/4 metrics computed
[TASK 6] Synthesize validated evidence into the final report
[RESULT] heuristic competitor candidates: Nimbus Compute, Helix Silicon, Quanta Forge Labs
[TASK 6] COMPLETED - extractive: 3 competitors, 3 developments, 5 signals, 2 risks
[RESULT] status=completed | tasks 6/6 | tool calls=14 | failures=3 | recoveries=2 | sources=5
[RESULT] Saved /home/claude/competitive-intelligence-agent/runs/20260927-112456_research-recent-developments-of-voltaic-/report.json, /home/claude/competitive-intelligence-agent/runs/20260927-112456_research-recent-developments-of-voltaic-/report.md

# Competitive Landscape Report

> **OFFLINE SYNTHETIC MODE** - all companies, sources and figures below come from a fictional test corpus (`data/synthetic_corpus.json`). Not real information.

**Goal:** Research recent developments of Voltaic Semiconductors  
**Status:** `completed`  
**Generated:** 2026-09-27T11:24:56 | planner: `template` | LLM: `none` | synthesis: extractive (no LLM): findings are sentences quoted from sources; competitor list is heuristic

> Legend: bullet points ending in `[S#]` are **sourced facts** (see Sources). Lines marked *Analysis* are **inference** by the agent.

## Target Company

Voltaic Semiconductors

## Executive Summary

*Analysis:* Evidence base: 5 sources (4 full pages, 1 snippet-only) about Voltaic Semiconductors. Companies/alternatives appearing in competitive contexts: Nimbus Compute, Helix Silicon, Quanta Forge Labs. Collected 3 development, 5 competitive-signal and 2 risk statements. Example computed metric: Voltaic Semiconductors: revenue growth vs prior period = 80.4%. (Auto-generated overview without an LLM; see cited statements below.)

## Major Competitors

- **Nimbus Compute** - Nimbus Compute unveiled its MX3 accelerator, positioning the chip as a lower-cost alternative to Voltaic's Arc line for large-model training. [S3][S4][S5]
- **Helix Silicon** - Voltaic Semiconductors remains the market leader, with rivals Nimbus Compute, Helix Silicon and Quanta Forge Labs competing for share. [S3]
- **Quanta Forge Labs** - Voltaic Semiconductors remains the market leader, with rivals Nimbus Compute, Helix Silicon and Quanta Forge Labs competing for share. [S3]

## Recent Developments

- Voltaic Semiconductors announced a partnership with Orbital Networks to build sovereign AI data centers in three countries. [S2]
- Nimbus Compute unveiled its MX3 accelerator, positioning the chip as a lower-cost alternative to Voltaic's Arc line for large-model training. [S4]
- Voltaic said the partnership expands its presence in government and telecom markets. [S2]

## Competitive Signals

- Voltaic Semiconductors remains the market leader, with rivals Nimbus Compute, Helix Silicon and Quanta Forge Labs competing for share. [S3]
- Voltaic Semiconductors reported data-center revenue of $18.4 billion for fiscal 2025, up from $10.2 billion in fiscal 2024. [S1]
- Nimbus Compute reported accelerator revenue of $4.1 billion in 2025, up from $2.3 billion in 2024. [S4]
- Nimbus Compute said two major cloud customers have committed to deploying MX3 clusters next year. [S4]
- Independent benchmarks published this month compare Voltaic's Arc 4 with the Nimbus Compute MX3 on training and inference tasks. [S5]

### Computed Metrics (calculator tool)

| Metric | Value | Expression | Inputs from |
|---|---|---|---|
| Voltaic Semiconductors: revenue growth vs prior period | 80.39% | `(18.4 - 10.2) / 10.2 * 100` | [S1] |
| Nimbus Compute: revenue growth vs prior period | 78.26% | `(4.1 - 2.3) / 2.3 * 100` | [S4] |
| Voltaic Semiconductors: share of combined reported revenue of companies found (not total market share) | 81.78% | `18.4 / (18.4 + 4.1) * 100` | [S1][S4] |
| Nimbus Compute: share of combined reported revenue of companies found (not total market share) | 18.22% | `4.1 / (18.4 + 4.1) * 100` | [S1][S4] |

_Values are computed deterministically from figures stated in the cited sources; they inherit those sources' definitions and periods._

## Risks / Challenges

- Supply of advanced packaging and high-bandwidth memory remains the main constraint on industry growth. [S3]
- The company acknowledged that its software ecosystem remains less mature than Voltaic's, which remains a barrier to adoption for some customers. [S4]

## Sources

- **[S1]** [SYNTHETIC] Voltaic Semiconductors posts record data-center revenue - <https://synthetic.example/voltaic-fy2025-results> (search snippet only)
- **[S2]** [SYNTHETIC] Voltaic announces sovereign AI data-center partnership with Orbital Networks - <https://synthetic.example/voltaic-orbital-partnership> (full page)
- **[S3]** [SYNTHETIC] AI accelerator market overview: Voltaic leads, rivals close in - <https://synthetic.example/ai-accelerator-market-overview> (full page)
- **[S4]** [SYNTHETIC] Nimbus Compute unveils MX3 accelerator to challenge Voltaic - <https://synthetic.example/nimbus-mx3-launch> (full page)
- **[S5]** [SYNTHETIC] Voltaic vs Nimbus Compute: benchmark comparison of Arc 4 and MX3 - <https://synthetic.example/voltaic-vs-nimbus-benchmarks> (full page)

## Agent Execution Summary

- Tasks: 6/6 completed, 0 failed
- Tools used: calculator, url_fetcher, web_search
- Tool calls: 14 | failures detected: 3 | recoveries: 2
- Sources analyzed: 5 | duration: 1.01s

| # | Task | Tool | Status | Note |
|---|---|---|---|---|
| 1 | Research recent developments for Voltaic Semiconductors | web_search | completed_with_recovery | 5 results via retry |
| 2 | Find recent announcements and product news for Voltaic Semiconductors | web_search | completed | 5 results via first_try |
| 3 | Find competitive context for Voltaic Semiconductors | web_search | completed | 5 results via first_try |
| 4 | Retrieve and read the most relevant public sources | url_fetcher | completed_with_recovery | 4 full pages, 1 snippet fallbacks, 0 skipped |
| 5 | Compute comparable metrics from figures stated in sources | calculator | completed | 4/4 metrics computed |
| 6 | Synthesize validated evidence into the final report | synthesize | completed | extractive: 3 competitors, 3 developments, 5 signals, 2 risks |

**Failures and recoveries:**

- `failure` (task 1, web_search): web_search: invalid tool response: missing "results" [malformed_response]
- `recovery` (task 1, web_search): Recovered via retry (attempt 2/2)
- `failure` (task 4, url_fetcher): url_fetcher: request timed out (ReadTimeout) [timeout]
- `failure` (task 4, url_fetcher): url_fetcher: request timed out (ReadTimeout) [timeout]
- `gave_up` (task 4, url_fetcher): Giving up after 2 attempt(s): request timed out (ReadTimeout)
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S1 instead of full page

```
