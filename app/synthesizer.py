"""Turn validated sources + metrics into a ReportBody.

* LLMSynthesizer        – LLM writes the analysis as JSON; citations are then
                          enforced deterministically (unknown source ids removed,
                          uncited "facts" relabelled as inference).
* ExtractiveSynthesizer – no-LLM fallback: selects sentences verbatim from the
                          sources, so every finding is a quoted, cited fact.
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import ValidationError

from app.llm import LLMClient, LLMError, extract_json
from app.models.plan import AnalysisType, Objective
from app.models.report import CompetitorEntry, Finding, Metric, ReportBody, Source
from app.text_utils import COMPETITIVE_CUE, mentions, relevant_excerpt, split_sentences
from app.validator import relevance_terms
from app.validator import ResultValidator

_DEV = re.compile(r"\b(launch\w*|announc\w*|unveil\w*|introduc\w*|releas\w*|partner\w*|"
                  r"acquir\w*|expand\w*|shipping|funding|raised)\b", re.I)
_SIGNAL = re.compile(r"\b(market share|share|revenue|growth|demand|customers?|pric\w*|"
                     r"adopt\w*|benchmarks?|leader|orders?|lower-cost)\b", re.I)
_RISK = re.compile(r"\b(risks?|export|restrict\w*|regulat\w*|shortage|constrain\w*|lawsuit|"
                   r"antitrust|delay\w*|barrier|pressure|declin\w*|less mature|limited)\b", re.I)


class Synthesizer(Protocol):
    name: str
    notes: list[str]

    def synthesize(self, objective: Objective, sources: list[Source], metrics: list[Metric],
                   competitors: list[str]) -> ReportBody: ...


class ExtractiveSynthesizer:
    name = "extractive"

    def __init__(self, per_section: int = 5) -> None:
        self.per_section = per_section
        self.notes: list[str] = []

    def synthesize(self, objective: Objective, sources: list[Source], metrics: list[Metric],
                   competitors: list[str]) -> ReportBody:
        targets = objective.target_entities
        buckets: dict[str, list[tuple[int, int, Finding]]] = {"risk": [], "dev": [], "sig": []}
        seen: set[str] = set()
        order = 0
        for src in sources:
            for sent in split_sentences(src.content):
                key = sent.lower()
                if key in seen:
                    continue
                seen.add(key)
                score = (2 * sum(mentions(sent, t) for t in targets)
                         + sum(mentions(sent, c) for c in competitors))
                finding = Finding(text=sent, source_ids=[src.id], kind="fact")
                order += 1
                if _RISK.search(sent):
                    buckets["risk"].append((score, -order, finding))
                elif _DEV.search(sent):
                    buckets["dev"].append((score, -order, finding))
                elif _SIGNAL.search(sent):
                    buckets["sig"].append((score, -order, finding))

        def top(name: str) -> list[Finding]:
            ranked = sorted(buckets[name], key=lambda x: (x[0], x[1]), reverse=True)
            return [f for _, _, f in ranked[: self.per_section]]

        comp_names = self._competitor_names(objective, competitors)
        comp_entries = [self._competitor_entry(n, sources) for n in comp_names]
        body = ReportBody(
            target_company=", ".join(targets),
            executive_summary="",
            competitors=comp_entries,
            recent_developments=top("dev"),
            market_signals=top("sig"),
            risks=top("risk"),
            synthesis_method="extractive (no LLM): findings are sentences quoted from sources; "
                             "competitor list is heuristic",
        )
        body.executive_summary = self._summary(objective, sources, metrics, body)
        return body

    @staticmethod
    def _competitor_names(objective: Objective, detected: list[str]) -> list[str]:
        names = list(objective.target_entities[1:]) if (
            objective.analysis_type == AnalysisType.COMPARISON) else []
        for d in detected:
            if d not in names and not any(mentions(t, d.split()[0]) for t in objective.target_entities):
                names.append(d)
        return names[:6]

    @staticmethod
    def _competitor_entry(name: str, sources: list[Source]) -> CompetitorEntry:
        ids: list[int] = []
        best: tuple[int, str] = (-1, "")
        for src in sources:
            for sent in split_sentences(src.content):
                if not mentions(sent, name):
                    continue
                if src.id not in ids:
                    ids.append(src.id)
                # prefer sentences with a competitive cue where the company is the subject
                rank = (2 if COMPETITIVE_CUE.search(sent) else 0) + (
                    1 if sent.lower().startswith(name.lower()) else 0)
                if rank > best[0]:
                    best = (rank, sent)
        summary = best[1]
        return CompetitorEntry(name=name, summary=summary, source_ids=ids[:3],
                               kind="fact" if ids else "inference")

    @staticmethod
    def _summary(objective: Objective, sources: list[Source], metrics: list[Metric],
                 body: ReportBody) -> str:
        full = sum(1 for s in sources if s.retrieval == "full_page")
        snip = len(sources) - full
        comps = ", ".join(c.name for c in body.competitors) or "none identified"
        ok_metrics = [m for m in metrics if m.status == "ok" and m.value is not None]
        metric_txt = ""
        if ok_metrics:
            m = ok_metrics[0]
            metric_txt = f" Example computed metric: {m.label} = {m.value:.1f}{m.unit}."
        return (
            f"Evidence base: {len(sources)} sources ({full} full pages, {snip} snippet-only) "
            f"about {', '.join(objective.target_entities)}"
            f"{' (market: ' + objective.market + ')' if objective.market else ''}. "
            f"Companies/alternatives appearing in competitive contexts: {comps}. "
            f"Collected {len(body.recent_developments)} development, "
            f"{len(body.market_signals)} competitive-signal and {len(body.risks)} risk statements."
            f"{metric_txt} (Auto-generated overview without an LLM; see cited statements below.)"
        )


SYNTH_SYSTEM = """You are the reporting module of a competitive-intelligence agent.
Write a concise, neutral brief using ONLY the numbered sources and computed metrics given.
Rules:
- Every item with kind "fact" MUST cite source ids from the list, e.g. "source_ids": [2, 5].
- Your own analysis/interpretation must use kind "inference" (source_ids may support it).
- Never invent sources, numbers, products or events. If evidence is thin, say so.
Return ONLY JSON:
{"executive_summary": str,
 "competitors": [{"name": str, "summary": str, "source_ids": [int], "kind": "fact|inference"}],
 "recent_developments": [{"text": str, "source_ids": [int], "kind": "fact|inference"}],
 "market_signals": [...same shape...],
 "risks": [...same shape...]}
Max 5 items per list; each text is ONE short sentence."""


class LLMSynthesizer:
    name = "llm"

    def __init__(self, llm: LLMClient, validator: ResultValidator,
                 fallback: ExtractiveSynthesizer | None = None, max_retries: int = 1) -> None:
        self.llm, self.validator = llm, validator
        self.fallback = fallback or ExtractiveSynthesizer()
        self.max_retries = max_retries
        self.notes: list[str] = []

    def synthesize(self, objective: Objective, sources: list[Source], metrics: list[Metric],
                   competitors: list[str]) -> ReportBody:
        prompt = self._prompt(objective, sources, metrics, competitors)
        for attempt in range(1, self.max_retries + 2):
            try:
                data = extract_json(self.llm.complete(SYNTH_SYSTEM, prompt, max_tokens=1500))
                data["target_company"] = ", ".join(objective.target_entities)
                data["synthesis_method"] = f"llm ({self.llm.name}); citations enforced"
                body = ReportBody.model_validate(data)
                body, issues = self.validator.enforce_citations(
                    body, {s.id for s in sources}, {s.id: s.content for s in sources})
                self.notes.extend(issues)
                if attempt > 1:
                    self.notes.append(f"LLM synthesis succeeded on retry {attempt - 1}")
                return body
            except (LLMError, ValidationError, TypeError) as e:
                self.notes.append(f"LLM synthesis attempt {attempt} failed: {type(e).__name__}")
        self.notes.append("Fell back to extractive synthesis")
        return self.fallback.synthesize(objective, sources, metrics, competitors)

    @staticmethod
    def _prompt(objective: Objective, sources: list[Source], metrics: list[Metric],
                competitors: list[str]) -> str:
        terms = relevance_terms(objective.target_entities, objective.market)
        src_txt = "\n\n".join(
            f"[{s.id}] {s.title} ({s.url}) [{s.retrieval}]\n"
            f"{relevant_excerpt(s.content, terms, 1200)}" for s in sources)
        met_txt = "\n".join(f"- {m.label}: {m.value:.2f}{m.unit} (sources {m.source_ids})"
                            for m in metrics if m.status == "ok" and m.value is not None)
        return (f"Goal: {objective.raw_goal}\nTarget(s): {', '.join(objective.target_entities)}\n"
                f"Analysis type: {objective.analysis_type.value}\nMarket: {objective.market}\n"
                "Identify competitors yourself from the sources.\n\n"
                f"Computed metrics:\n{met_txt or '(none)'}\n\nSources:\n{src_txt}")
