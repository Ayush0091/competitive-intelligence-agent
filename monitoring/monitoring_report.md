# Monitoring report

Generated 2026-09-28 14:54 by `python scripts/monitor.py` from 21 saved runs (`runs/*/report.json` + `trace.jsonl`). All figures are counted from those files.

## Health summary

| Metric | Value |
|---|---|
| Runs | 21 (18 completed, 3 failed) |
| Run success rate | 86% |
| Tool calls / failures / recoveries / abandoned | 219 / 63 / 27 / 42 |
| Sources analysed / metrics computed | 95 / 29 |
| Deliberately injected faults | 12 |
| Run duration p50 / p95 | 378s / 534s |
| LLM calls, latency p50 / p95 | 64, 104.9s / 231.3s |
| Share of runtime spent waiting on the LLM | 98% |

## Alerts

| Check | Status | Detail |
|---|---|---|
| Run success rate | **ALERT** | 86% (threshold >= 90%) |
| Run success rate, last 10 runs | OK | 100% |
| Tool success rate: calculator | OK | 100% of 29 calls; last 10 runs 100% (threshold >= 80%) |
| Tool success rate: url_fetcher | **ALERT** | 73% of 100 calls; last 10 runs 76% (threshold >= 80%) |
| Tool success rate: web_search | **ALERT** | 60% of 90 calls; last 10 runs 91% (threshold >= 80%) |
| LLM p95 latency | **ALERT** | 231.3s (threshold <= 120s) |
| Run p95 duration | OK | 534s (threshold <= 600s) |
| Abandoned tool calls per run | OK | 2.0 (threshold <= 3) |

## Tools

| Tool | Calls | Success rate | Success, last 10 runs | p50 latency | p95 latency |
|---|---|---|---|---|---|
| calculator | 29 | 100% | 100% | 0 ms | 0 ms |
| url_fetcher | 100 | 73% | 76% | 492 ms | 1894 ms |
| web_search | 90 | 60% | 91% | 721 ms | 2681 ms |

## LLM calls by purpose

| Purpose | Calls | p50 | p95 | mean |
|---|---|---|---|---|
| figure extraction | 17 | 110.4s | 247.1s | 137.2s |
| plan | 20 | 101.7s | 111.2s | 102.1s |
| re-plan | 10 | 10.8s | 14.7s | 10.7s |
| synthesis (brief) | 17 | 177.2s | 190.0s | 174.0s |

## Errors by tool and type

| Error | Count |
|---|---|
| web_search: http_error | 30 |
| url_fetcher: http_error | 14 |
| url_fetcher: timeout | 10 |
| web_search: malformed_response | 6 |
| url_fetcher: empty_result | 3 |

## Recovery events

| Event kind | Count |
|---|---|
| info | 74 |
| failure | 63 |
| gave_up | 42 |
| fallback | 22 |
| recovery | 5 |

## Search providers that returned results

| Provider | Searches |
|---|---|
| tavily | 36 |
| duckduckgo | 18 |

## Per run

| Run | Goal | Status | Tasks | Calls | Fail | Recov | Gave up | Faults | Re-plans | Sources | Metrics | LLM s | Total s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260927-135901 | Analyze the competitive landscape of NVIDIA i | failed | 0/6 | 9 | 9 | 0 | 6 | 0 | 3 | 0 | 0 | 131 | 133 |
| 20260927-140117 | Compare NVIDIA and AMD in AI accelerators | failed | 0/7 | 12 | 12 | 0 | 8 | 0 | 4 | 0 | 0 | 157 | 160 |
| 20260927-140359 | Research recent developments of AMD in AI acc | failed | 0/5 | 10 | 10 | 0 | 6 | 2 | 3 | 0 | 0 | 108 | 110 |
| 20260927-142131 | Analyze the competitive landscape of NVIDIA i | completed | 6/6 | 9 | 1 | 1 | 1 | 0 | 0 | 5 | 1 | 373 | 378 |
| 20260927-142752 | Compare NVIDIA and AMD in AI accelerators | completed | 6/6 | 11 | 2 | 2 | 2 | 0 | 0 | 6 | 2 | 317 | 323 |
| 20260927-143319 | Research recent developments of AMD in AI acc | completed | 5/6 | 10 | 4 | 3 | 2 | 2 | 0 | 5 | 0 | 329 | 334 |
| 20260927-144714 | Analyze the competitive landscape of NVIDIA i | completed | 6/6 | 9 | 1 | 1 | 1 | 0 | 0 | 5 | 1 | 356 | 360 |
| 20260927-145317 | Compare NVIDIA and AMD in AI accelerators | completed | 5/6 | 9 | 0 | 0 | 0 | 0 | 0 | 6 | 0 | 382 | 387 |
| 20260927-145948 | Research recent developments of AMD in AI acc | completed | 5/6 | 10 | 4 | 3 | 2 | 2 | 0 | 5 | 0 | 321 | 326 |
| 20260927-163643 | Analyze the competitive landscape of NVIDIA i | completed | 5/6 | 8 | 1 | 1 | 1 | 0 | 0 | 5 | 0 | 288 | 297 |
| 20260927-164144 | Compare NVIDIA and AMD in AI accelerators | completed | 6/6 | 14 | 3 | 3 | 3 | 0 | 0 | 6 | 5 | 393 | 404 |
| 20260927-164831 | Research recent developments of AMD in AI acc | completed | 6/6 | 15 | 3 | 2 | 1 | 2 | 0 | 5 | 5 | 404 | 418 |
| 20260927-165814 | Analyze the competitive landscape of NVIDIA i | completed | 6/6 | 12 | 1 | 1 | 1 | 0 | 0 | 5 | 4 | 555 | 564 |
| 20260927-170742 | Compare NVIDIA and AMD in AI accelerators | completed | 6/6 | 10 | 2 | 2 | 2 | 0 | 0 | 6 | 1 | 502 | 511 |
| 20260927-171617 | Research recent developments of AMD in AI acc | completed | 5/6 | 10 | 3 | 2 | 1 | 2 | 0 | 5 | 0 | 404 | 411 |
| 20260927-172644 | Analyze the competitive landscape of NVIDIA i | completed | 6/6 | 12 | 0 | 0 | 0 | 0 | 0 | 5 | 4 | 501 | 510 |
| 20260927-173518 | Compare NVIDIA and AMD in AI accelerators | completed | 6/6 | 11 | 1 | 1 | 1 | 0 | 0 | 6 | 2 | 520 | 531 |
| 20260927-174412 | Research recent developments of AMD in AI acc | completed | 5/6 | 10 | 3 | 2 | 1 | 2 | 0 | 5 | 0 | 518 | 526 |
| 20260927-175652 | Analyze the competitive landscape of NVIDIA i | completed | 6/6 | 11 | 0 | 0 | 0 | 0 | 0 | 5 | 3 | 523 | 534 |
| 20260927-180549 | Compare NVIDIA and AMD in AI accelerators | completed | 6/6 | 9 | 2 | 2 | 2 | 0 | 0 | 5 | 1 | 359 | 366 |
| 20260928-145114 | show-report "Compare NVIDIA and AMD in AI acc | completed | 5/6 | 8 | 1 | 1 | 1 | 0 | 0 | 5 | 0 | 0 | 12 |
