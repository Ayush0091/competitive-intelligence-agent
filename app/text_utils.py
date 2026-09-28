"""Small deterministic text helpers used by the no-LLM fallbacks."""

from __future__ import annotations

import re
from collections import Counter

from app.models.report import Source

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9&\-]+(?:\s+[A-Z][A-Za-z0-9&\-]+){0,2})")
COMPETITIVE_CUE = re.compile(
    r"\b(rivals?|compet(?:e|es|ing|itors?)|alternative to|challeng(?:e|es|ed|er|ers)|"
    r"versus|vs\.?|in-house)\b", re.I)
_STOPWORDS = {
    "the", "in", "its", "it", "however", "analysts", "analyst", "management", "independent",
    "reviewers", "regulators", "industry", "supply", "several", "suppliers", "company",
    "meanwhile", "according", "earlier", "last", "this", "that", "these", "those", "he", "she",
    "they", "we", "our", "a", "an", "and", "but", "for", "with", "while", "after", "before",
    "during", "new", "first", "second", "ai", "gpu", "gpus", "cpu", "ceo", "cfo", "us", "eu",
    "uk", "inc", "corp", "ltd", "llc", "synthetic", "observers", "customers", "chips", "some",
    "many", "most", "both", "other", "all", "on", "at", "as", "by", "from", "if", "when",
    "what", "who", "why", "how", "where", "which", "usd", "eur", "inr", "gbp", "asic",
    "asics", "fpga", "fpgas", "tpu", "tpus", "npu", "npus", "hbm", "api", "cloud", "data",
}
# Names ending in these words are usually analyst firms or media outlets quoted in
# articles, not competitors.
_NON_COMPETITOR_SUFFIX = {"research", "analytics", "securities", "capital", "advisors",
                          "consulting", "insights", "intelligence", "news", "times", "journal",
                          "reuters", "bloomberg", "partners", "associates", "institute"}


def split_sentences(
    text: str, min_len: int = 40, max_len: int = 400, require_terminal: bool = True
) -> list[str]:
    """Split text into sentences; by default drop headline/menu fragments without end punctuation."""
    out: list[str] = []
    for line in text.splitlines():
        for s in _SENT_SPLIT.split(line.strip()):
            s = s.strip()
            if not (min_len <= len(s) <= max_len):
                continue
            if require_terminal and not s.endswith((".", "!", "?", ".\"", ".'")):
                continue
            out.append(s)
    return out


def relevant_excerpt(text: str, terms: set[str], max_chars: int = 1200) -> str:
    """The most informative lines of a page, in original order, within a char budget.

    Pages often start with navigation or cookie text; a local 8B model reads a short
    prompt much faster, so we send the lines that mention the objective's terms or
    contain figures instead of simply the first N characters.
    """
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 40]
    if not lines:
        return text[:max_chars]

    def score(line: str) -> int:
        low = line.lower()
        return 3 * sum(t in low for t in terms) + (2 if re.search(r"\d", line) else 0)

    ranked = sorted(range(len(lines)), key=lambda i: (-score(lines[i]), i))
    chosen, used = [], 0
    for i in ranked:
        if used + len(lines[i]) > max_chars:
            continue
        chosen.append(i)
        used += len(lines[i]) + 1
    return "\n".join(lines[i] for i in sorted(chosen)) or text[:max_chars]


def mentions(sentence: str, name: str) -> bool:
    return re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", sentence, re.I) is not None


def _strip_stop(tokens: list[str]) -> list[str]:
    while tokens and tokens[0].lower() in _STOPWORDS:
        tokens = tokens[1:]
    while tokens and tokens[-1].lower() in _STOPWORDS:
        tokens = tokens[:-1]
    return tokens


def detect_companies(sources: list[Source], exclude: list[str], limit: int = 6) -> list[str]:
    """Heuristically find organisation names that appear in competitive contexts.

    This is a fallback for when no LLM is configured; it is intentionally
    conservative and its output is labelled as heuristic in the report.
    """
    counts: Counter[str] = Counter()
    cue_hits: Counter[str] = Counter()
    product_like: set[str] = set()
    for src in sources:
        text = src.content
        for sent in split_sentences(text, min_len=20, require_terminal=False):
            has_cue = bool(COMPETITIVE_CUE.search(sent))
            for m in _NAME_RE.finditer(sent):
                tokens = _strip_stop(m.group(1).split())
                if not tokens:
                    continue
                preceding = sent[max(0, m.start() - 6): m.start()].lower()
                for n in range(1, len(tokens) + 1):
                    name = " ".join(tokens[:n])
                    counts[name] += 1
                    if has_cue:
                        cue_hits[name] += 1
                    if n == 1 and re.search(r"('s|’s|the|its)\s$", preceding):
                        product_like.add(name)

    excluded_first = {e.split()[0].lower() for e in exclude if e}
    chosen: list[str] = []
    for first, first_count in counts.most_common():
        if " " in first or first.lower() in excluded_first or first.lower() in _STOPWORDS:
            continue
        # extend to the longest multi-word name that carries most of the mentions
        best = first
        for name, c in counts.items():
            if name.startswith(first + " ") and c >= 0.6 * first_count and len(name) > len(best):
                best = name
        if any(ch.isdigit() for ch in best) or cue_hits[best] == 0:
            continue
        if best.split()[-1].lower() in _NON_COMPETITOR_SUFFIX:
            continue
        single = " " not in best
        if single and (best in product_like or counts[best] < 3 or len(best) < 3):
            continue
        if best not in chosen:
            chosen.append(best)
        if len(chosen) >= limit:
            break
    return chosen
