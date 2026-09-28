# Evaluation report

Generated 2026-09-28 14:54 by `python scripts/evaluate.py`. Offline and deterministic: fictional synthetic corpus, no LLM, no network. Every number below is computed from the labelled traces in `evaluation/traces/`.

## 1. Failure detection and recovery (fault-injection matrix)

- Runs: **111** = 3 goals x (1 clean + 3 tools x 6 failure modes x 2 durations). Transient = first call faulty; persistent = every call faulty.
- Tool calls labelled: **1563**. Ground truth comes from the harness (the fault injector and the corpus's known HTTP 503 page); the agent's prediction is whether its validator flagged the call. The agent is never told.

| Failure detection (per tool call) | Value |
|---|---|
| Precision (flagged calls that were really faulty) | **100.0%** |
| Recall (faulty calls that were flagged) | **100.0%** |
| F1 | 100.0% |
| TP / FP / FN / TN | 453 / 0 / 0 / 1110 |

| Fault type | Detected / total |
|---|---|
| injected:bad_json | 81 / 81 |
| injected:crash | 81 / 81 |
| injected:empty | 60 / 60 |
| injected:http_error | 81 / 81 |
| injected:malformed | 69 / 69 |
| injected:timeout | 81 / 81 |

| Run outcome | Value |
|---|---|
| Runs where the injected fault fired | 108 |
| ...of which the faulted step still produced a result (recovered) | **90 / 108** |
| Runs that finished with status `completed` | 93 / 111 |
| Agent crashes | 0 |
| Clean runs completed | 3 / 3 |

Not recovered (18 runs): `G1-calculator-malformed-persistent`, `G1-calculator-empty-persistent`, `G1-calculator-timeout-persistent`, `G1-calculator-http_error-persistent`, `G1-calculator-bad_json-persistent`, `G1-calculator-crash-persistent`, `G2-calculator-malformed-persistent`, `G2-calculator-empty-persistent`, `G2-calculator-timeout-persistent`, `G2-calculator-http_error-persistent`, `G2-calculator-bad_json-persistent`, `G2-calculator-crash-persistent`, `G3-calculator-malformed-persistent`, `G3-calculator-empty-persistent`, `G3-calculator-timeout-persistent`, `G3-calculator-http_error-persistent`, `G3-calculator-bad_json-persistent`, `G3-calculator-crash-persistent`

These are persistent calculator outages. The calculator has no fallback tool, so the metric step is marked failed; the agent still finishes, writes the brief from the sources and reports status `completed_with_warnings` instead of crashing or inventing numbers (graceful degradation, not recovery).

## 2. Numeric-grounding guard (hallucinated numbers)

Positive class = claim contains a figure the source does not support. `validator.ungrounded_numbers` flags a claim if any of its figures is not literally present in the source.

| Set | n | Precision | Recall | F1 | TP/FP/FN/TN |
|---|---|---|---|---|---|
| Core cases | 20 | 100.0% | 100.0% | 100.0% | 10/0/0/10 |
| All incl. blind-spot probes | 27 | 76.9% | 71.4% | 74.1% | 10/3/4/10 |

| Case | Label | Flagged | Correct | Probe | Unmatched numbers |
|---|---|---|---|---|---|
| g01 | grounded | False | yes |  |  |
| g02 | grounded | False | yes |  |  |
| g03 | hallucinated | True | yes |  | 19.1 |
| g04 | hallucinated | True | yes |  | 80 |
| g05 | grounded | False | yes |  |  |
| g06 | hallucinated | True | yes |  | 343 |
| g07 | grounded | False | yes |  |  |
| g08 | hallucinated | True | yes |  | 256 |
| g09 | grounded | False | yes |  |  |
| g10 | hallucinated | True | yes |  | 92 |
| g11 | grounded | False | yes |  |  |
| g12 | grounded | False | yes |  |  |
| g13 | hallucinated | True | yes |  | 12 |
| g14 | grounded | False | yes |  |  |
| g15 | hallucinated | True | yes |  | 5.5 |
| g16 | grounded | False | yes |  |  |
| g17 | hallucinated | True | yes |  | 57 |
| g18 | grounded | False | yes |  |  |
| g19 | hallucinated | True | yes |  | 1.5 |
| g20 | hallucinated | True | yes |  | 460 |
| p01 | grounded | True | **no** | unit conversion | 18400 |
| p02 | grounded | True | **no** | rounding | 431.7 |
| p03 | hallucinated | False | **no** | misattributed figure |  |
| p04 | hallucinated | False | **no** | wrong period |  |
| p05 | hallucinated | False | **no** | single-digit figure |  |
| p06 | grounded | True | **no** | number written as a word | 12 |
| p07 | hallucinated | False | **no** | invented year |  |

## 3. Metric sanity check (nonsense calculations)

Positive class = invalid metric. `metrics.is_well_formed` runs on every metric the LLM path produces, before the calculator.

| Set | n | Precision | Recall | F1 | TP/FP/FN/TN |
|---|---|---|---|---|---|
| Core cases | 19 | 100.0% | 100.0% | 100.0% | 9/0/0/10 |
| All incl. probes | 22 | 100.0% | 75.0% | 85.7% | 9/0/3/10 |

Mistake patterns reproduced from real qwen3:8b runs: 6 / 6 classified correctly.

| Case | Origin | Label | Flagged | Correct | Reason |
|---|---|---|---|---|---|
| m01 | hand | valid | False | yes |  |
| m02 | hand | valid | False | yes |  |
| m03 | hand | valid | False | yes |  |
| m04 | hand | valid | False | yes |  |
| m05 | hand | valid | False | yes |  |
| m06 | hand | valid | False | yes |  |
| m07 | hand | valid | False | yes |  |
| m08 | live-run | valid | False | yes |  |
| m09 | hand | valid | False | yes |  |
| m10 | hand | valid | False | yes |  |
| m11 | live-run | invalid | True | yes | not a calculation (a single copied number) |
| m12 | live-run | invalid | True | yes | combines fewer than two distinct source figures (e.g. 40 - 40) |
| m13 | live-run | invalid | True | yes | labelled CAGR but has no exponent (that is total growth) |
| m14 | live-run | invalid | True | yes | a division yields a ratio or percentage, but the unit is 'GB' (use %, x or none) |
| m15 | live-run | invalid | True | yes | divides a figure by itself |
| m16 | hand | invalid | True | yes | combines fewer than two distinct source figures (e.g. 40 - 40) |
| m17 | hand | invalid | True | yes | unit is % but the expression never multiplies by 100 |
| m18 | hand | invalid | True | yes | combines fewer than two distinct source figures (e.g. 40 - 40) |
| m19 | hand | invalid | True | yes | divides a figure by itself |
| p01 | probe | invalid | False | **no** | two-company share mislabelled as whole-market share (semantic error) |
| p02 | probe | invalid | False | **no** | old and new values swapped |
| p03 | probe | invalid | False | **no** | subtracts GB from USD (unit mix-up) |

## Honest reading

- Suite 1 measures the validator + recovery loop on synthetic faults. Real-web faults are messier; see the monitoring report for live-run numbers.
- Detection is 100% because every injected fault is visible to the deterministic validator (error status, wrong shape, empty result). Faults that look valid - e.g. a well-formed page with wrong facts - are out of scope for this suite; suites 2-3 cover that risk.
- Suites 2-3 use small hand-labelled sets written by the author (n is small, so treat the percentages as indicative, not statistically strong).
- The probes show known blind spots: literal matching cannot catch a real number attached to the wrong company or period, and it flags valid unit conversions. Semantic errors in metrics (wrong label, swapped operands) are not caught by syntax checks; the design limits them by having Python, not the LLM, build the formulas.
