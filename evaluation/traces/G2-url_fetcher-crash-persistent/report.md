# Competitive Landscape Report

> **OFFLINE SYNTHETIC MODE** - all companies, sources and figures below come from a fictional test corpus (`data/synthetic_corpus.json`). Not real information.

**Goal:** Compare Voltaic Semiconductors and Nimbus Compute in AI accelerators  
**Status:** `completed`  
**Generated:** 2026-09-28T14:54:02 | planner: `template` | LLM: `none` | synthesis: extractive (no LLM): findings are sentences quoted from sources; competitor list is heuristic

> Legend: bullet points ending in `[S#]` are **sourced facts** (see Sources). Lines marked *Analysis* are **inference** by the agent.

## Target Company

Voltaic Semiconductors, Nimbus Compute

## Executive Summary

*Analysis:* Evidence base: 5 sources (0 full pages, 5 snippet-only) about Voltaic Semiconductors, Nimbus Compute (market: AI accelerators). Companies/alternatives appearing in competitive contexts: Nimbus Compute. Collected 2 development, 2 competitive-signal and 0 risk statements. Example computed metric: Voltaic Semiconductors: revenue growth vs prior period = 80.4%. (Auto-generated overview without an LLM; see cited statements below.)

## Major Competitors

- **Nimbus Compute** - Nimbus Compute unveiled its MX3 accelerator, positioning the chip as a lower-cost alternative to Voltaic's Arc line for large-model training. [S1][S4]

## Recent Developments

- Nimbus Compute unveiled its MX3 accelerator, positioning the chip as a lower-cost alternative to Voltaic's Arc line for large-model training. [S1]
- Voltaic Semiconductors announced a partnership with Orbital Networks to build sovereign AI data centers in three countries. [S3]

## Competitive Signals

- Independent benchmarks published this month compare Voltaic's Arc 4 with the Nimbus Compute MX3 on training and inference tasks. [S4]
- Voltaic Semiconductors reported data-center revenue of $18.4 billion for fiscal 2025, up from $10.2 billion in fiscal 2024. [S5]

### Computed Metrics (calculator tool)

| Metric | Value | Expression | Inputs from |
|---|---|---|---|
| Voltaic Semiconductors: revenue growth vs prior period | 80.39% | `(18.4 - 10.2) / 10.2 * 100` | [S5] |

_Values are computed deterministically from figures stated in the cited sources; they inherit those sources' definitions and periods._

## Risks / Challenges

_No risks found in the retrieved sources._

## Sources

- **[S1]** [SYNTHETIC] Nimbus Compute unveils MX3 accelerator to challenge Voltaic - <https://synthetic.example/nimbus-mx3-launch> (search snippet only)
- **[S2]** [SYNTHETIC] AI accelerator market overview: Voltaic leads, rivals close in - <https://synthetic.example/ai-accelerator-market-overview> (search snippet only)
- **[S3]** [SYNTHETIC] Voltaic announces sovereign AI data-center partnership with Orbital Networks - <https://synthetic.example/voltaic-orbital-partnership> (search snippet only)
- **[S4]** [SYNTHETIC] Voltaic vs Nimbus Compute: benchmark comparison of Arc 4 and MX3 - <https://synthetic.example/voltaic-vs-nimbus-benchmarks> (search snippet only)
- **[S5]** [SYNTHETIC] Voltaic Semiconductors posts record data-center revenue - <https://synthetic.example/voltaic-fy2025-results> (search snippet only)

## Agent Execution Summary

- Tasks: 6/6 completed, 0 failed
- Tools used: calculator, url_fetcher, web_search
- Tool calls: 14 | failures detected: 10 | recoveries: 5
- Sources analyzed: 5 | duration: 0.01s

| # | Task | Tool | Status | Note |
|---|---|---|---|---|
| 1 | Find head-to-head comparisons of Voltaic Semiconductors and Nimbus Compute | web_search | completed | 5 results via first_try |
| 2 | Research recent developments for Voltaic Semiconductors | web_search | completed | 5 results via first_try |
| 3 | Research recent developments for Nimbus Compute | web_search | completed | 5 results via first_try |
| 4 | Retrieve and read the most relevant public sources | url_fetcher | completed_with_recovery | 0 full pages, 5 snippet fallbacks, 0 skipped |
| 5 | Compute comparable metrics from figures stated in sources | calculator | completed | 1/1 metrics computed |
| 6 | Synthesize validated evidence into the final report | synthesize | completed | extractive: 1 competitors, 2 developments, 2 signals, 0 risks |

**Failures and recoveries:**

- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `gave_up` (task 4, url_fetcher): Giving up after 2 attempt(s): RuntimeError: injected tool crash
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S1 instead of full page
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `gave_up` (task 4, url_fetcher): Giving up after 2 attempt(s): RuntimeError: injected tool crash
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S2 instead of full page
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `gave_up` (task 4, url_fetcher): Giving up after 2 attempt(s): RuntimeError: injected tool crash
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S3 instead of full page
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `gave_up` (task 4, url_fetcher): Giving up after 2 attempt(s): RuntimeError: injected tool crash
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S4 instead of full page
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `failure` (task 4, url_fetcher): url_fetcher: RuntimeError: injected tool crash [unknown]
- `gave_up` (task 4, url_fetcher): Giving up after 2 attempt(s): RuntimeError: injected tool crash
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S5 instead of full page
