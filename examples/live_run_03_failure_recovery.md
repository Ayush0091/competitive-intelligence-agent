# Live run 3 - Deliberately induced failures + recovery

> **Data mode: LIVE.** Real web search/fetch; LLM as configured in `.env`.

**Command:**

```bash
python main.py --inject-failure web_search:malformed --inject-failure url_fetcher:timeout:2 --show-report "Research recent developments of AMD in AI accelerators"
```

**Exit code:** 0

**Console transcript (verbatim):**

```text
[AGENT] LLM health check: Ollama OK at http://localhost:11434; model 'qwen3:8b' is installed
[AGENT] Goal received: "Research recent developments of AMD in AI accelerators"
[AGENT] mode=live | llm=ollama:qwen3:8b | search=web_search[tavily]
[FAULT] Deliberate failure armed: web_search -> 'malformed' for the next 1 call(s) (validator is not told)
[FAULT] Deliberate failure armed: url_fetcher -> 'timeout' for the next 2 call(s) (validator is not told)
[LLM] ollama:qwen3:8b answered in 104.4s (1436 chars) - You are the planning module of a competitive-intelligence ag

============================================================
AGENT EXECUTION PLAN
============================================================

Goal:
  Research recent developments of AMD in AI accelerators

Interpreted objective:
  type=developments  targets=AMD  market=AI accelerators

Planner: llm (LLM ollama:qwen3:8b)

Tasks:
  [1] Search for recent news on AMD's AI accelerators
       -> web_search (query="AMD AI accelerators recent developments 2026")
  [2] Search for AMD's AI accelerator product launches
       -> web_search (query="AMD AI accelerator product launches 2026")
  [3] Search for AMD's AI accelerator partnerships and collaborations
       -> web_search (query="AMD AI accelerator partnerships 2026")
  [4] Fetch the most relevant sources
       -> url_fetcher (inputs from tasks [1, 2, 3])
  [5] Compute metrics from the sources
       -> calculator (inputs from tasks [4])
  [6] Write the report on AMD's recent developments in AI accelerators
       -> synthesize (inputs from tasks [4, 5])

Tools:
  ✓ Web Search
  ✓ URL Fetcher
  ✓ Calculator

Execution mode:
  Sequential | every tool result validated | recovery enabled (retries=1, fallbacks on, LLM re-planning on)
============================================================

[PLAN] 6 tasks generated; executing sequentially
[TASK 1] Search for recent news on AMD's AI accelerators
[TOOL] web_search[tavily] query="AMD AI accelerators recent developments 2026" (attempt 1)
[ERROR] invalid tool response: missing "results" [malformed_response]
[RECOVERY] Validation failed. Retry attempt 1/1 in 0.5s...
[TOOL] web_search[tavily] query="AMD AI accelerators recent developments 2026" (attempt 2)
[VALIDATION] passed in 1989 ms
[RECOVERY] Recovered via retry (attempt 2/2)
[RESULT] 5 valid results (provider=tavily)
[RESULT]   - AMD's next-generation AI chips set to power 2026 data ... | https://www.spglobal.com/market-intelligence/en/news-insights/research/2026/03/amd-s-next-generation-ai-chips-set-to-power-2026-data-center-growth
[RESULT]   - AMD Delivers Full-Stack Compute for the Agentic AI Era | https://ir.amd.com/news-events/press-releases/detail/1294/aai-2026-amd-delivers-full-stack-compute-for-the-agentic-ai-era
[RESULT]   - Advancing AI 2026: AMD Begins & Ends the Show with ... | https://www.abiresearch.com/blog/amd-ai-strategy-advancing-day-2026
[RESULT]   - Advancing AI 2026 Replay | Build What's Next with @AMD | https://www.youtube.com/watch?v=8B_Gese-bdI
[RESULT]   - AMD Advancing AI 2026 | San Francisco, July 22-23 | https://www.amd.com/en/corporate/events/advancing-ai.html
[TASK 1] COMPLETED_WITH_RECOVERY - 5 results via retry
[TASK 2] Search for AMD's AI accelerator product launches
[TOOL] web_search[tavily] query="AMD AI accelerator product launches 2026" (attempt 1)
[VALIDATION] passed in 1590 ms
[RESULT] 5 valid results (provider=tavily)
[RESULT]   - AMD Delivers Full-Stack Compute for the Agentic AI Era | https://ir.amd.com/news-events/press-releases/detail/1294/aai-2026-amd-delivers-full-stack-compute-for-the-agentic-ai-era
[RESULT]   - Advancing AI 2026: AMD Begins & Ends the Show with ... | https://www.abiresearch.com/blog/amd-ai-strategy-advancing-day-2026
[RESULT]   - AMD at CES 2026 | https://www.amd.com/en/partner/browse-by-resource/partner-insights-articles/ces-2026-ai-ecosystem.html
[RESULT]   - Upcoming Hardware Launches 2026 (Updated Jul 2026) | https://www.techpowerup.com/review/future-hardware-releases
[RESULT]   - AMD Advancing AI 2026: Does AMD Now Build the World's ... | https://futurumgroup.com/insights/amd-advancing-ai-2026-does-amd-now-build-the-worlds-best-cpus-and-gpus
[TASK 2] COMPLETED - 5 results via first_try
[TASK 3] Search for AMD's AI accelerator partnerships and collaborations
[TOOL] web_search[tavily] query="AMD AI accelerator partnerships 2026" (attempt 1)
[VALIDATION] passed in 1171 ms
[RESULT] 5 valid results (provider=tavily)
[RESULT]   - Advancing AI 2026: AMD Begins & Ends the Show with ... | https://www.abiresearch.com/blog/amd-ai-strategy-advancing-day-2026
[RESULT]   - AMD Delivers Full-Stack Compute for the Agentic AI Era | https://ir.amd.com/news-events/press-releases/detail/1294/aai-2026-amd-delivers-full-stack-compute-for-the-agentic-ai-era
[RESULT]   - Oracle and AMD Expand Partnership to Help Customers ... | https://www.oracle.com/news/announcement/ai-world-oracle-and-amd-expand-partnership-to-help-customers-achieve-next-generation-ai-scale-2025-10-14
[RESULT]   - AMD Advancing AI 2026 | San Francisco, July 22-23 | https://www.amd.com/en/corporate/events/advancing-ai.html
[RESULT]   - Advancing AI 2026 Replay | Build What's Next with @AMD | https://www.youtube.com/watch?v=8B_Gese-bdI
[TASK 3] COMPLETED - 5 results via first_try
[TASK 4] Fetch the most relevant sources
[TOOL] url_fetcher url="https://www.spglobal.com/market-intelligence/en/news-insights/research/2026/03/amd-s-next-..." (attempt 1)
[ERROR] request timed out (ReadTimeout) [timeout]
[RECOVERY] Tool call failed. Retry attempt 1/1 in 0.5s...
[TOOL] url_fetcher url="https://www.spglobal.com/market-intelligence/en/news-insights/research/2026/03/amd-s-next-..." (attempt 2)
[ERROR] request timed out (ReadTimeout) [timeout]
[RECOVERY] Giving up after 2 attempt(s): request timed out (ReadTimeout)
[RECOVERY] Degraded gracefully: using search snippet for S1 instead of full page
[TOOL] url_fetcher url="https://ir.amd.com/news-events/press-releases/detail/1294/aai-2026-amd-delivers-full-stack..." (attempt 1)
[VALIDATION] passed in 633 ms (warnings: 1)
[RESULT] S2: 21731 chars extracted (truncated)
[TOOL] url_fetcher url="https://www.abiresearch.com/blog/amd-ai-strategy-advancing-day-2026" (attempt 1)
[VALIDATION] passed in 493 ms (warnings: 1)
[RESULT] S3: 15031 chars extracted (truncated)
[TOOL] url_fetcher url="https://www.amd.com/en/partner/browse-by-resource/partner-insights-articles/ces-2026-ai-ec..." (attempt 1)
[VALIDATION] passed in 322 ms
[RESULT] S4: 6535 chars extracted
[TOOL] url_fetcher url="https://www.oracle.com/news/announcement/ai-world-oracle-and-amd-expand-partnership-to-hel..." (attempt 1)
[VALIDATION] passed in 862 ms (warnings: 1)
[RESULT] S5: 9885 chars extracted (truncated)
[TASK 4] COMPLETED_WITH_RECOVERY - 4 full pages, 1 snippet fallbacks, 0 skipped
[TASK 5] Compute metrics from the sources
[LLM] ollama:qwen3:8b answered in 223.6s (2378 chars) - You extract quantitative FACTS from numbered sources for a c
[VALIDATION] dropped figure 'AMD market size': value 2000 not found in source 2
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 1
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 2
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 2
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 4
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 5
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 2
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 4
[VALIDATION] dropped figure 'AMD product launch': value 1 not found in source 5
[VALIDATION] LLM extracted 15 figure(s), 6 grounded in their sources
[VALIDATION] no comparable figure pairs from the LLM; deterministic extractor found 0 metric(s)
[TASK 5] SKIPPED - no comparable figure pairs from the LLM; deterministic extractor found 0 metric(s) (nothing computed)
[TASK 6] Write the report on AMD's recent developments in AI accelerators
[LLM] ollama:qwen3:8b answered in 190.0s (2401 chars) - You are the reporting module of a competitive-intelligence a
[VALIDATION] 'fact' relabelled as inference - figure(s) ['450'] not in cited source(s): AMD launched the Instinct MI400 series and Helios rack-scale
[TASK 6] COMPLETED - llm: 2 competitors, 3 developments, 3 signals, 3 risks
[RESULT] status=completed | tasks 5/6 | tool calls=10 | failures=3 | recoveries=2 | sources=5
[RESULT] Saved E:\Assignment\competitive-intelligence-agent\runs\20260927-174412_research-recent-developments-of-amd-in-a\report.json, E:\Assignment\competitive-intelligence-agent\runs\20260927-174412_research-recent-developments-of-amd-in-a\report.md

# Competitive Landscape Report

**Goal:** Research recent developments of AMD in AI accelerators  
**Status:** `completed`  
**Generated:** 2026-09-27T17:44:16 | planner: `llm` | LLM: `ollama:qwen3:8b` | synthesis: llm (ollama:qwen3:8b); citations enforced

> Legend: bullet points ending in `[S#]` are **sourced facts** (see Sources). Lines marked *Analysis* are **inference** by the agent.

## Target Company

AMD

## Executive Summary

*Analysis:* AMD is launching next-generation AI accelerators, including the Instinct MI450 and MI430X, targeting data centers and sovereign AI markets, with partnerships and product expansions in 2026.

## Major Competitors

- **Nvidia** - AMD is challenging Nvidia's dominance in the AI accelerator market with its MI400 series and Helios platform. *(analysis)*
- **Oracle** - Oracle is deploying AMD's Instinct MI450 GPUs in its AI supercluster, indicating strong industry adoption. [S5]

## Recent Developments

- *Analysis:* AMD launched the Instinct MI400 series and Helios rack-scale solutions at Advancing AI 2026, with MI450 and MI430X variants in production. (supported by [S2])
- AMD's MI455X accelerators feature 432 GB of HBM4 memory, offering 50% more capacity than previous generations. [S3]
- Oracle will deploy 50,000 AMD Instinct MI450 GPUs in its AI supercluster starting in Q3 2026. [S5]

## Competitive Signals

- *Analysis:* AMD's AI accelerators are positioned to support exascale-class supercomputers and sovereign AI initiatives. (supported by [S2])
- AMD's full-stack AI offerings are expected to drive its total addressable market to $2 trillion by 2030. [S2]
- AMD's AI PC portfolio includes new Ryzen AI platforms with up to 60 TOPs NPU performance. [S4]

_No metrics were computed: no comparable figure pairs from the LLM; deterministic extractor found 0 metric(s) (nothing computed)._

## Risks / Challenges

- *Analysis:* AMD faces competition from Nvidia, which continues to dominate the AI accelerator market. (supported by [S1])
- *Analysis:* The success of AMD's MI400 series depends on its ability to meet the diverse needs of sovereign AI and HPC customers. (supported by [S3])
- *Analysis:* AMD's expansion into AI infrastructure may require significant investment in R&D and manufacturing.

## Sources

- **[S1]** AMD's next-generation AI chips set to power 2026 data ... - <https://www.spglobal.com/market-intelligence/en/news-insights/research/2026/03/amd-s-next-generation-ai-chips-set-to-power-2026-data-center-growth> (search snippet only)
- **[S2]** AAI 2026: AMD Delivers Full-Stack Compute for the Agentic AI Era :: Advanced Micro Devices, Inc. (AMD) - <https://ir.amd.com/news-events/press-releases/detail/1294/aai-2026-amd-delivers-full-stack-compute-for-the-agentic-ai-era> (full page)
- **[S3]** Advancing AI 2026: AMD Begins & Ends the Show with Confidence - <https://www.abiresearch.com/blog/amd-ai-strategy-advancing-day-2026> (full page)
- **[S4]** AMD at CES 2026 - <https://www.amd.com/en/partner/browse-by-resource/partner-insights-articles/ces-2026-ai-ecosystem.html> (full page)
- **[S5]** Oracle and AMD Expand Partnership to Help Customers Achieve Next-Generation AI Scale - <https://www.oracle.com/news/announcement/ai-world-oracle-and-amd-expand-partnership-to-help-customers-achieve-next-generation-ai-scale-2025-10-14> (full page)

## Agent Execution Summary

- Tasks: 5/6 completed, 0 failed
- Tools used: url_fetcher, web_search
- Tool calls: 10 | failures detected: 3 | recoveries: 2
- Sources analyzed: 5 | duration: 526.18s

| # | Task | Tool | Status | Note |
|---|---|---|---|---|
| 1 | Search for recent news on AMD's AI accelerators | web_search | completed_with_recovery | 5 results via retry |
| 2 | Search for AMD's AI accelerator product launches | web_search | completed | 5 results via first_try |
| 3 | Search for AMD's AI accelerator partnerships and collaborations | web_search | completed | 5 results via first_try |
| 4 | Fetch the most relevant sources | url_fetcher | completed_with_recovery | 4 full pages, 1 snippet fallbacks, 0 skipped |
| 5 | Compute metrics from the sources | calculator | skipped | no comparable figure pairs from the LLM; deterministic extractor found 0 metric(s) (nothing computed) |
| 6 | Write the report on AMD's recent developments in AI accelerators | synthesize | completed | llm: 2 competitors, 3 developments, 3 signals, 3 risks |

**Failures and recoveries:**

- `failure` (task 1, web_search): web_search: invalid tool response: missing "results" [malformed_response]
- `recovery` (task 1, web_search): Recovered via retry (attempt 2/2)
- `failure` (task 4, url_fetcher): url_fetcher: request timed out (ReadTimeout) [timeout]
- `failure` (task 4, url_fetcher): url_fetcher: request timed out (ReadTimeout) [timeout]
- `gave_up` (task 4, url_fetcher): Giving up after 2 attempt(s): request timed out (ReadTimeout)
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S1 instead of full page

```
