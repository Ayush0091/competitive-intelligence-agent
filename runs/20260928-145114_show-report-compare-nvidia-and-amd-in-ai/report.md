# Competitive Landscape Report

**Goal:** show-report "Compare NVIDIA and AMD in AI accelerators  
**Status:** `completed`  
**Generated:** 2026-09-28T14:51:24 | planner: `template` | LLM: `none` | synthesis: extractive (no LLM): findings are sentences quoted from sources; competitor list is heuristic

> Legend: bullet points ending in `[S#]` are **sourced facts** (see Sources). Lines marked *Analysis* are **inference** by the agent.

## Target Company

Compare NVIDIA, AMD

## Executive Summary

*Analysis:* Evidence base: 5 sources (4 full pages, 1 snippet-only) about Compare NVIDIA, AMD (market: AI accelerators). Companies/alternatives appearing in competitive contexts: AMD, NVLink, Llama, Tensor Cores, June, Market Reality. Collected 5 development, 5 competitive-signal and 5 risk statements. (Auto-generated overview without an LLM; see cited statements below.)

## Major Competitors

- **AMD** - AMD vs NVIDIA GPU: Which Performs Better for AI Workloads? [S1][S2][S3]
- **NVLink** - : 288GB HBM3E, 8 TB/s bandwidth, ~4,600 TFLOPS FP8 — AMD leads on memory capacity, NVIDIA leads on NVLink interconnect (1.8 TB/s vs ~128 GB/s). [S2][S4]
- **Llama** - achieved near-parity with B200 on Llama 2 70B LoRA (10.18 min vs 9.85 min). [S4]
- **Tensor Cores** - At the hardware level, teams often reduce the comparison to Tensor Cores versus Matrix Cores. [S1][S2]
- **June** - AMD launched MI300 for AI training workloads in June 2023 and is competing with NVIDIA for market share. [S2]
- **Market Reality** -  *(analysis)*

## Recent Developments

- AMD launched MI300 for AI training workloads in June 2023 and is competing with NVIDIA for market share. [S2]
- In June 2026 AMD announced the acquisition of MEXT, whose predictive-memory technology is designed to make flash behave more like DRAM and cut data center memory cost. [S2]
- AMD launched the Instinct MI350X and MI355X on June 12, 2025 at Advancing AI 2025. [S2]
- At GTC on March 16, 2026 NVIDIA expanded it to seven chips, the Vera CPU, Rubin GPU, NVLink 6 Switch, ConnectX-9 SuperNIC, BlueField-4 DPU, Spectrum-6 Ethernet switch and Groq 3 LPU, and declared them in full production. [S2]
- In 2025, AMD acquired a team of AI hardware and software engineers from Untether AI along with compiler startup Brium. [S2]

## Competitive Signals

- NVIDIA holds the crown with its mature CUDA ecosystem and dominant market share, but AMD’s Instinct line is rapidly closing the gap, offering greater memory capacity, open-source flexibility, and competitive performance at lower cost. [S1]
- NVIDIA is the scale leader in AI infrastructure, and AMD is the focused challenger. [S1]
- Morgan Stanley put NVIDIA at roughly 85% of AI processor revenue in March 2026, with custom ASICs above 10% and AMD below 5%. [S2]
- NVIDIA holds ~80% of the AI accelerator market by revenue with $193.7B in FY2026 data center sales, versus AMD's estimated 5-7% share (~$7-8B in Instinct revenue). [S4]
- The bigger structural threat to NVIDIA is custom silicon — Broadcom AI ASIC revenue hit $20B+ in FY2025 — not AMD. [S4]

_No metrics were computed: no comparable numeric figures found in sources (nothing computed)._

## Risks / Challenges

- A key insight is that NVIDIA’s market lead maps directly to lower integration risk, while AMD’s value shows up when you have a narrower use case and the engineering discipline to stay inside it. [S1]
- Prominent Chinese technology companies, including Alibaba and Baidu, are increasingly switching from Nvidia hardware to internally developed chips as U.S. export controls restrict the capabilities of Nvidia's offerings in the country. [S5]
- Resumed shipments to China, following regulatory clearances for the H20 and other GPUs, are seen by names like Goldman Sachs as a potential $2 billion to $5 billion near-term revenue tailwind. [S5]
- The risk that institutions remain underweight in the stock relative to S&P 500 benchmarks is also flagged as a potential headwind should sentiment shift or market leadership rotate away from AI. [S5]
- Regulatory and competitive pressures in China continue to mount. [S5]

## Sources

- **[S1]** AMD vs NVIDIA GPU: Which Performs Better for AI Workloads? - Fluence Cloud - <https://fluence.ai/blog/amd-vs-nvidia-gpu> (full page)
- **[S2]** Top 30+ AI Chip Makers: NVIDIA & Its Competitors - <https://aimultiple.com/ai-chip-makers> (full page)
- **[S3]** AMD introduces new AI accelerators and networking solutions - <https://au.investing.com/news/company-news/amd-introduces-new-ai-accelerators-and-networking-solutions-93CH-3481604> (search snippet only)
- **[S4]** AMD vs NVIDIA AI GPU Market Share 2026: MI350X vs B200 - <https://siliconanalysts.com/analysis/amd-vs-nvidia-ai-gpu-market-share-2026> (full page)
- **[S5]** How Recent Developments Are Shaping the NVIDIA Investment Story - <https://finance.yahoo.com/news/recent-developments-shaping-nvidia-investment-113602034.html> (full page)

## Agent Execution Summary

- Tasks: 5/6 completed, 0 failed
- Tools used: url_fetcher, web_search
- Tool calls: 8 | failures detected: 1 | recoveries: 1
- Sources analyzed: 5 | duration: 11.72s

| # | Task | Tool | Status | Note |
|---|---|---|---|---|
| 1 | Find head-to-head comparisons of Compare NVIDIA and AMD | web_search | completed | 5 results via first_try |
| 2 | Research recent developments for Compare NVIDIA | web_search | completed | 5 results via first_try |
| 3 | Research recent developments for AMD | web_search | completed | 5 results via first_try |
| 4 | Retrieve and read the most relevant public sources | url_fetcher | completed_with_recovery | 4 full pages, 1 snippet fallbacks, 0 skipped |
| 5 | Compute comparable metrics from figures stated in sources | calculator | skipped | no comparable numeric figures found in sources (nothing computed) |
| 6 | Synthesize validated evidence into the final report | synthesize | completed | extractive: 6 competitors, 5 developments, 5 signals, 5 risks |

**Failures and recoveries:**

- `failure` (task 4, url_fetcher): url_fetcher: HTTP 403 Forbidden [http_error]
- `gave_up` (task 4, url_fetcher): Giving up after 1 attempt(s): HTTP 403 Forbidden
- `fallback` (task 4, url_fetcher): Degraded gracefully: using search snippet for S3 instead of full page
