"""Turn figures stated in sources into calculator expressions.

The LLM only *extracts* labelled figures (each value must appear in its cited
source); deterministic code derives growth / CAGR / share expressions from them,
and the calculator tool evaluates those. A regex extractor is the no-LLM fallback.
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLMClient, LLMError, extract_json
from app.models.plan import Objective
from app.models.report import Source
from app.text_utils import mentions, relevant_excerpt, split_sentences
from app.validator import relevance_terms

_MONEY = re.compile(r"\$\s?(\d+(?:\.\d+)?)\s*(billion|million|bn|m)\b", re.I)
_GROWTH_CUE = re.compile(r"\b(up from|down from|compared (?:with|to)|versus)\b", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_ALLOWED_CONSTANTS = {"100", "1", "2", "1000"}


class MetricRequest(BaseModel):
    label: str = Field(min_length=3, max_length=160)
    expression: str = Field(min_length=1, max_length=200)
    unit: str = ""
    source_ids: list[int] = Field(default_factory=list)


class MetricExtractor(Protocol):
    name: str

    def extract(self, objective: Objective, sources: list[Source],
                entities: list[str]) -> list[MetricRequest]: ...


def _fmt(v: float) -> str:
    return f"{v:g}"


class RegexMetricExtractor:
    """Deterministic fallback: revenue growth and share-of-combined-revenue."""

    name = "regex"

    def __init__(self, max_metrics: int = 6) -> None:
        self.max_metrics = max_metrics

    def extract(self, objective: Objective, sources: list[Source],
                entities: list[str]) -> list[MetricRequest]:
        out: list[MetricRequest] = []
        revenue: dict[str, tuple[float, int]] = {}
        for src in sources:
            for sent in split_sentences(src.content):
                if "revenue" not in sent.lower():
                    continue
                amounts = [float(v) / (1000 if u.lower() in ("million", "m") else 1)
                           for v, u in _MONEY.findall(sent)]
                if not amounts:
                    continue
                entity = _first_entity(sent, entities)
                if entity is None:
                    continue
                if len(amounts) >= 2 and _GROWTH_CUE.search(sent) and amounts[1] > 0:
                    a, b = amounts[0], amounts[1]
                    out.append(MetricRequest(
                        label=f"{entity}: revenue growth vs prior period",
                        expression=f"({_fmt(a)} - {_fmt(b)}) / {_fmt(b)} * 100",
                        unit="%", source_ids=[src.id]))
                revenue.setdefault(entity, (amounts[0], src.id))
        if len(revenue) >= 2:
            total = " + ".join(_fmt(v) for v, _ in revenue.values())
            ids = sorted({sid for _, sid in revenue.values()})
            for entity, (v, _) in revenue.items():
                out.append(MetricRequest(
                    label=f"{entity}: share of combined reported revenue of companies found "
                          f"(not total market share)",
                    expression=f"{_fmt(v)} / ({total}) * 100", unit="%", source_ids=ids))
        return _dedupe(out)[: self.max_metrics]


def _first_entity(sentence: str, entities: list[str]) -> str | None:
    found = [(sentence.lower().find(e.split()[0].lower()), e) for e in entities
             if mentions(sentence, e) or mentions(sentence, e.split()[0])]
    found = [f for f in found if f[0] >= 0]
    return min(found)[1] if found else None


def _dedupe(items: list[MetricRequest]) -> list[MetricRequest]:
    seen: set[str] = set()
    out = []
    for m in items:
        if m.label not in seen:
            seen.add(m.label)
            out.append(m)
    return out


FIGURE_SYSTEM = """You extract quantitative FACTS from numbered sources for a competitive-intelligence
report. Do NOT calculate anything - a separate calculator derives metrics from your figures.
Return ONLY JSON: {"figures": [{"entity": str, "metric": str, "value": number, "unit": str,
"period": str, "source_id": int}]}
Rules:
- Copy each value exactly as written in the source (no rounding, no conversion).
- One figure per item. Max 15 items. Prefer figures about the target entities and market.
- Use short, consistent metric names so figures can be compared, e.g. "revenue",
  "data-center revenue", "market size", "market share", "memory capacity".
- unit examples: "billion USD", "million USD", "%", "GB". period: the year or quarter the
  figure refers to ("2025", "Q2 2026"), or "" if the source does not say.
- Use the same entity spelling every time (e.g. always "AMD")."""


class Figure(BaseModel):
    entity: str = Field(min_length=1, max_length=80)
    metric: str = Field(min_length=1, max_length=80)
    value: float
    unit: str = ""
    period: str = ""
    source_id: int


def _value_forms(v: float) -> set[str]:
    forms = {f"{v:g}", f"{v:.1f}", f"{v:.2f}"}
    if float(v).is_integer():
        forms.add(str(int(v)))
    return forms


def figure_is_grounded(fig: Figure, sources_by_id: dict[int, Source]) -> tuple[bool, str]:
    src = sources_by_id.get(fig.source_id)
    if src is None:
        return False, f"cites unknown source {fig.source_id}"
    text = src.content.replace(",", "")
    if not any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", text) for f in _value_forms(fig.value)):
        return False, f"value {fig.value:g} not found in source {fig.source_id}"
    return True, ""


def _period_key(period: str) -> tuple[int, int] | None:
    year = re.search(r"(19|20)\d\d", period)
    if not year:
        return None
    q = re.search(r"\bQ([1-4])\b", period, re.I)
    return int(year.group(0)), int(q.group(1)) if q else 0


_ADDITIVE = re.compile(r"revenue|sales|shipment|units? sold|spend|capex|capital expenditure|"
                       r"income|profit|bookings|orders|market size|sold", re.I)


def _subject(f: Figure) -> str:
    """'AMD data-center revenue', but just 'market size' for generic market entities."""
    ent = f.entity.strip()
    if ent.lower() in ("market", "industry", "sector", "global", "total") or \
            ent.lower() in f.metric.lower():
        return f.metric
    return f"{ent} {f.metric}"


def derive_metrics(figures: list[Figure], limit: int = 6) -> list[MetricRequest]:
    """Deterministically turn extracted figures into comparable metrics.

    * growth  - same entity + metric + unit at two periods: (new - old) / old * 100
    * CAGR    - same, when the periods are >= 2 years apart
    * change  - for figures already in %, the difference in percentage points
    * share   - additive metric (revenue, shipments...) + unit + period for >= 2 entities:
                part / total * 100
    * ratio   - non-additive metric (e.g. memory capacity) for 2 entities: a / b
    """
    norm = lambda t: re.sub(r"\s+", " ", t.strip().lower())  # noqa: E731
    out: list[MetricRequest] = []

    series: dict[tuple[str, str, str], list[tuple[tuple[int, int], Figure]]] = {}
    for f in figures:
        key = _period_key(f.period)
        if key is not None and f.value > 0:
            series.setdefault((norm(f.entity), norm(f.metric), norm(f.unit)), []).append((key, f))
    for (_, metric, unit), points in series.items():
        points.sort(key=lambda p: p[0])
        (k0, old), (k1, new) = points[0], points[-1]
        if k0 == k1 or old.value == new.value:
            continue
        ids = sorted({old.source_id, new.source_id})
        span = f"{old.period} to {new.period}"
        if unit in ("%", "percent"):
            out.append(MetricRequest(
                label=f"{_subject(new)}: change {span}", unit="pp", source_ids=ids,
                expression=f"{_fmt(new.value)} - {_fmt(old.value)}"))
            continue
        out.append(MetricRequest(
            label=f"{_subject(new)}: growth {span}", unit="%", source_ids=ids,
            expression=f"({_fmt(new.value)} - {_fmt(old.value)}) / {_fmt(old.value)} * 100"))
        years = k1[0] - k0[0]
        if years >= 2:
            out.append(MetricRequest(
                label=f"{_subject(new)}: CAGR {span}", unit="%", source_ids=ids,
                expression=f"(({_fmt(new.value)} / {_fmt(old.value)}) ** (1 / {years}) - 1) * 100"))

    # Shares only make sense for quantities that add up across companies (revenue,
    # shipments...). For specs such as memory capacity, compare two companies with a ratio.
    groups: dict[tuple[str, str, str], dict[str, Figure]] = {}
    for f in figures:
        if norm(f.unit) in ("%", "percent") or f.value <= 0:
            continue
        groups.setdefault((norm(f.metric), norm(f.unit), norm(f.period)), {}).setdefault(
            norm(f.entity), f)
    for (metric, _, period), by_entity in groups.items():
        if len(by_entity) < 2:
            continue
        figs = list(by_entity.values())
        if not _ADDITIVE.search(metric):
            hi, lo = sorted(figs, key=lambda f: f.value, reverse=True)[:2]
            if lo.value > 0 and hi.value != lo.value:
                out.append(MetricRequest(
                    label=f"{hi.entity} vs {lo.entity}: {hi.metric} ratio"
                          f"{' (' + hi.period + ')' if hi.period else ''}",
                    expression=f"{_fmt(hi.value)} / {_fmt(lo.value)}", unit="x",
                    source_ids=sorted({hi.source_id, lo.source_id})))
            continue
        total = " + ".join(_fmt(f.value) for f in figs)
        ids = sorted({f.source_id for f in figs})
        for f in figs:
            out.append(MetricRequest(
                label=(f"{f.entity}: share of combined {f.metric}{' ' + f.period if f.period else ''}"
                       f" among {len(figs)} companies found (not total market)"),
                expression=f"{_fmt(f.value)} / ({total}) * 100", unit="%", source_ids=ids))
    return _dedupe(out)[:limit]


class LLMMetricExtractor:
    """The LLM extracts grounded figures; Python derives the metrics from them.

    Earlier versions let the LLM write arithmetic expressions. A live run with
    qwen3:8b produced expressions like "432 - 432 / (432 / 50)" and ratios reported
    in GB, so the model's job was narrowed to reading figures - the part it is good at.
    """

    name = "llm"

    def __init__(self, llm: LLMClient, fallback: RegexMetricExtractor | None = None) -> None:
        self.llm = llm
        self.fallback = fallback or RegexMetricExtractor()
        self.rejected: list[str] = []

    def extract(self, objective: Objective, sources: list[Source],
                entities: list[str]) -> list[MetricRequest]:
        terms = relevance_terms(objective.target_entities, objective.market)
        prompt = (f"Goal: {objective.raw_goal}\nTarget entities: {', '.join(entities)}\n\nSources:\n"
                  + "\n".join(f"[{s.id}] {s.title}\n{relevant_excerpt(s.content, terms, 1000)}"
                              for s in sources))
        try:
            data = extract_json(self.llm.complete(FIGURE_SYSTEM, prompt, max_tokens=900))
            raw = data.get("figures", [])
            figures = []
            for item in raw[:15]:
                try:
                    figures.append(Figure.model_validate(item))
                except ValidationError:
                    self.rejected.append("dropped figure: malformed item")
        except (LLMError, TypeError, AttributeError) as e:
            self.rejected.append(f"LLM figure extraction failed ({type(e).__name__}); used regex")
            return self.fallback.extract(objective, sources, entities)

        by_id = {s.id: s for s in sources}
        grounded: list[Figure] = []
        for f in figures:
            ok, reason = figure_is_grounded(f, by_id)
            if ok:
                grounded.append(f)
            else:
                self.rejected.append(f"dropped figure '{f.entity} {f.metric}': {reason}")
        self.rejected.append(f"LLM extracted {len(figures)} figure(s), {len(grounded)} grounded "
                             f"in their sources")
        metrics = [m for m in derive_metrics(grounded) if is_well_formed(m)[0]]
        if not metrics:
            fallback = self.fallback.extract(objective, sources, entities)
            self.rejected.append("no comparable figure pairs from the LLM; deterministic "
                                 f"extractor found {len(fallback)} metric(s)")
            return fallback
        return metrics


_OPERATOR = re.compile(r"[-+*/]")
_RATIO_UNITS = {"", "%", "x", "×", "ratio", "times", "pp", "percent"}


def is_well_formed(metric: MetricRequest) -> tuple[bool, str]:
    """Deterministic sanity checks on an LLM-proposed metric, beyond grounding.

    Catches mistakes seen with a real local model: a bare copied number presented as a
    computed metric, a figure combined with itself ("40 - 40") or divided by itself,
    a ratio reported in a physical unit ("256 / 128 = 2 GB"), a "%" metric that never multiplies by 100, and a "CAGR" with no
    exponent (which is total growth, not an annual rate).
    """
    expr = metric.expression.replace(" ", "")
    figures = set(_NUMBER.findall(expr)) - _ALLOWED_CONSTANTS
    if not _OPERATOR.search(expr.lstrip("-")) or len(_NUMBER.findall(expr)) < 2:
        return False, "not a calculation (a single copied number)"
    if len(figures) < 2:
        return False, "combines fewer than two distinct source figures (e.g. 40 - 40)"
    # x / x, or x / (x / y): meaningless. But x / (x + y) is a valid share, so allow +/-.
    if (re.search(r"(?<![\d.])(\d+(?:\.\d+)?)/\1(?![\d.])", expr)
            or re.search(r"(?<![\d.])(\d+(?:\.\d+)?)/\(\1(?![\d.])(?![+\-])", expr)):
        return False, "divides a figure by itself"
    unit = metric.unit.strip().lower()
    if "/" in expr and unit not in _RATIO_UNITS:
        return False, (f"a division yields a ratio or percentage, but the unit is "
                       f"'{metric.unit}' (use %, x or none)")
    if metric.unit.strip() == "%" and "100" not in expr:
        return False, "unit is % but the expression never multiplies by 100"
    if "cagr" in metric.label.lower() and "**" not in expr:
        return False, "labelled CAGR but has no exponent (that is total growth)"
    return True, ""


def is_grounded(metric: MetricRequest, sources_by_id: dict[int, Source]) -> tuple[bool, str]:
    """Every number in the expression must appear in a cited source's text."""
    cited = [sources_by_id[i] for i in metric.source_ids if i in sources_by_id]
    if not cited:
        return False, "cites no known source"
    corpus = " ".join(s.content for s in cited).replace(",", "")
    for num in _NUMBER.findall(metric.expression):
        if num in _ALLOWED_CONSTANTS:
            continue
        if not re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", corpus):
            return False, f"number {num} not found in cited sources"
    return True, ""
