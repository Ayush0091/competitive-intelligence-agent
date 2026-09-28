# Competitive Landscape Report

**Goal:** Compare NVIDIA and AMD in AI accelerators  
**Status:** `completed`  
**Generated:** 2026-09-27T14:27:56 | planner: `llm` | LLM: `ollama:qwen3:8b` | synthesis: llm (ollama:qwen3:8b); citations enforced

> Legend: bullet points ending in `[S#]` are **sourced facts** (see Sources). Lines marked *Analysis* are **inference** by the agent.

## Target Company

NVIDIA, AMD

## Executive Summary

*Analysis:* AMD's MI400 series is challenging NVIDIA's dominance in AI accelerators with competitive performance and memory bandwidth, while NVIDIA continues to lead with its Blackwell architecture.

## Major Competitors

- **NVIDIA** - NVIDIA leads in AI accelerators with its Blackwell architecture, including the B200 and B300 models. *(analysis)*
- **AMD** - AMD's MI400 series is a direct competitor to NVIDIA's Blackwell architecture, offering high performance and memory bandwidth. [S3]

## Recent Developments

- AMD's MI400 series is projected to generate $7.2 billion in revenue in H2 2026. [S3]
- AMD's MI400 series supports UALink, an open interconnect standard, challenging NVIDIA's NVLink. [S3]

## Competitive Signals

- *Analysis:* AMD's MI400 series is closing the performance gap with NVIDIA's Blackwell architecture. (supported by [S3])
- *Analysis:* AMD is positioning itself as a key player in the AI accelerator market with its MI400 and MI500 series. (supported by [S6])

### Computed Metrics (calculator tool)

| Metric | Value | Expression | Inputs from |
|---|---|---|---|
| AMD MI400 vs. NVIDIA Blackwell Performance Gap | 0.00PFLOPS | `40 - 40` | [S3] |
| AMD MI400 Memory Bandwidth Advantage | 0.00GB | `432 - 432` | [S3] |

_Values are computed deterministically from figures stated in the cited sources; they inherit those sources' definitions and periods._

## Risks / Challenges

- *Analysis:* NVIDIA's Blackwell architecture remains the default choice for AI data center deployments. (supported by [S3])
- *Analysis:* AMD's reliance on open standards may face challenges in a market dominated by proprietary solutions. (supported by [S3])

## Sources

- **[S1]** NVIDIA AI Accelerated Program | NVIDIA - <https://www.nvidia.com/en-in/ai-data-science/ai-accelerated/> (full page)
- **[S2]** AMD Products: Processors, Graphics, AI Accelerators and Adaptive Computing - <https://www.amd.com/en/products.html> (full page)
- **[S3]** AMD MI400 Series: $7.2B AI GPU Challenging Nvidia [2026] - <https://tech-insider.org/amd-mi400-series-ai-gpu-data-center-2026/> (full page)
- **[S4]** AI Solutions for Enterprises | NVIDIA - <https://www.nvidia.com/en-us/solutions/ai/> (full page)
- **[S5]** Accelerators - AMD - <https://www.amd.com/en/products/accelerators.html> (search snippet only)
- **[S6]** AMD's 2026-2027 AI Roadmap: Instinct MI400 & MI500 Target NVIDIA Dominance - <https://wccftech.com/amd-to-battle-nvidia-ai-dominance-instinct-mi400-accelerators-2026-mi500-2027/> (search snippet only)

## Agent Execution Summary

- Tasks: 6/6 completed, 0 failed
- Tools used: calculator, url_fetcher, web_search
- Tool calls: 11 | failures detected: 2 | recoveries: 2
- Sources analyzed: 6 | duration: 323.3s

| # | Task | Tool | Status | Note |
|---|---|---|---|---|
| 1 | Identify NVIDIA's AI accelerator offerings | web_search | completed | 5 results via first_try |
| 2 | Identify AMD's AI accelerator offerings | web_search | completed | 5 results via first_try |
| 3 | Find recent news on NVIDIA and AMD in AI accelerators | web_search | completed | 5 results via first_try |
| 4 | Read the most relevant sources | url_fetcher | completed_with_recovery | 4 full pages, 2 snippet fallbacks, 0 skipped |
| 5 | Compute comparable metrics | calculator | completed | 2/2 metrics computed |
| 6 | Write the competitive brief | synthesize | completed | llm: 2 competitors, 2 developments, 2 signals, 2 risks |

**Failures and recoveries:**

- `failure` (task 4, url_fetcher): url_fetcher: page had too little readable text (35 chars) [empty_result]
- `gave_up` (task 4, url_fetcher): Giving up after 1 attempt(s): page had too little readable text (35 chars)
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S5 instead of full page
- `failure` (task 4, url_fetcher): url_fetcher: HTTP 403 Forbidden [http_error]
- `gave_up` (task 4, url_fetcher): Giving up after 1 attempt(s): HTTP 403 Forbidden
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S6 instead of full page
