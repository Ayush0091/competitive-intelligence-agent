# Competitive Landscape Report

**Goal:** Compare NVIDIA and AMD in AI accelerators  
**Status:** `completed`  
**Generated:** 2026-09-27T17:35:21 | planner: `llm` | LLM: `ollama:qwen3:8b` | synthesis: llm (ollama:qwen3:8b); citations enforced

> Legend: bullet points ending in `[S#]` are **sourced facts** (see Sources). Lines marked *Analysis* are **inference** by the agent.

## Target Company

NVIDIA, AMD

## Executive Summary

*Analysis:* NVIDIA and AMD are leading the AI accelerator market, with NVIDIA holding ~80% of the data-center revenue share in FY2026, while AMD's share is estimated at 5-7%. AMD's MI325X and MI350X offer higher memory capacity and bandwidth compared to NVIDIA's B200 and H200, but NVIDIA's software maturity and interconnect technology provide a performance edge.

## Major Competitors

- **NVIDIA** - NVIDIA holds ~80% of the AI accelerator market by revenue with $193.7B in FY2026 data center sales. [S3]
- **AMD** - AMD's MI325X and MI350X accelerators offer higher memory capacity and bandwidth compared to NVIDIA's B200 and H200. *(analysis)*

## Recent Developments

- AMD introduced the Instinct MI325X accelerators with 256GB HBM3E memory and 6.0TB/s bandwidth. [S2]
- NVIDIA unveiled the Vera Rubin platform with the LPX inference accelerator, combining high-performance GPUs and LPUs. [S1]

## Competitive Signals

- AMD's market share in AI accelerators is estimated at 5-7% in FY2026, significantly lower than NVIDIA's 80%. [S3]
- AMD's MI350X matches NVIDIA's B200 on FP8 compute but exceeds it on memory capacity. [S3]

### Computed Metrics (calculator tool)

| Metric | Value | Expression | Inputs from |
|---|---|---|---|
| AMD: share of combined data-center revenue FY2026 among 2 companies found (not total market) | 3.49% | `7 / (193.7 + 7) * 100` | [S3] |
| AMD vs NVIDIA: memory capacity ratio | 1.33x | `256 / 192` | [S2][S3] |

_Values are computed deterministically from figures stated in the cited sources; they inherit those sources' definitions and periods._

## Risks / Challenges

- *Analysis:* NVIDIA's dominance is threatened by custom silicon from hyperscalers like Google and AWS, which collectively represent a faster-growing threat than AMD. (supported by [S3])
- *Analysis:* AMD's performance gap with NVIDIA is narrowing in memory capacity, but NVIDIA's software maturity and interconnect technology maintain a real-world performance edge. (supported by [S3])

## Sources

- **[S1]** Accelerating the Next Wave of AI Innovation | NVIDIA Data Center Products - <https://www.nvidia.com/en-us/data-center/products> (full page)
- **[S2]** AMD introduces new AI accelerators and networking solutions - <https://au.investing.com/news/company-news/amd-introduces-new-ai-accelerators-and-networking-solutions-93CH-3481604> (search snippet only)
- **[S3]** AMD vs NVIDIA AI GPU Market Share 2026: MI350X vs B200 - <https://siliconanalysts.com/analysis/amd-vs-nvidia-ai-gpu-market-share-2026> (full page)
- **[S4]** Top 12 NVIDIA GPUs for AI Training & Inference in 2026 - <https://www.atlantic.net/gpu-server-hosting/top-nvidia-gpus-for-ai-training-and-inference> (full page)
- **[S5]** AMD Delivers Leadership AI Performance with AMD Instinct MI325X Accelerators - <https://finance.yahoo.com/news/amd-delivers-leadership-ai-performance-180000934.html> (full page)
- **[S6]** menu - <https://intellectia.ai/blog/ai-chip-stocks-august-2026> (full page)

## Agent Execution Summary

- Tasks: 6/6 completed, 0 failed
- Tools used: calculator, url_fetcher, web_search
- Tool calls: 11 | failures detected: 1 | recoveries: 1
- Sources analyzed: 6 | duration: 531.44s

| # | Task | Tool | Status | Note |
|---|---|---|---|---|
| 1 | Identify NVIDIA's AI accelerator offerings | web_search | completed | 5 results via first_try |
| 2 | Identify AMD's AI accelerator offerings | web_search | completed | 5 results via first_try |
| 3 | Find recent news on NVIDIA and AMD in AI accelerators | web_search | completed | 5 results via first_try |
| 4 | Read the most relevant sources | url_fetcher | completed_with_recovery | 5 full pages, 1 snippet fallbacks, 0 skipped |
| 5 | Compute comparable metrics | calculator | completed | 2/2 metrics computed |
| 6 | Write the competitive brief | synthesize | completed | llm: 2 competitors, 2 developments, 2 signals, 2 risks |

**Failures and recoveries:**

- `failure` (task 4, url_fetcher): url_fetcher: HTTP 403 Forbidden [http_error]
- `gave_up` (task 4, url_fetcher): Giving up after 1 attempt(s): HTTP 403 Forbidden
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S2 instead of full page
