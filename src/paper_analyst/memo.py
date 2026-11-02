"""Structured research memo with strict separation of evidence and interpretation.

* ``SourceClaim`` - a VERBATIM quote from the source text (abstract or a
  user-supplied full text) plus a locator. Claims are validated against the
  source; anything that cannot be found verbatim is dropped and logged.
* ``Interpretation`` - an analyst/AI reading of the paper. Always labelled as
  such in the output and never presented as a finding of the paper.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .normalize import normalize_whitespace

SECTIONS: dict[str, str] = {
    "research_question": "Research question",
    "economic_mechanism": "Economic mechanism",
    "methodology": "Methodology",
    "data": "Data",
    "results": "Results",
    "limitations": "Limitations",
    "research_implications": "Research implications",
}

_ABBREV = re.compile(r"\b(e\.g|i\.e|et al|etc|vs|cf|Fig|Eq|No|approx)\.$", re.IGNORECASE)
_COUNTRY_ABBREV = re.compile(r"\b(U\.S|U\.K|E\.U)\.$")
_SENTENCE_STARTERS = {"we", "our", "the", "this", "these", "however", "in", "it", "a", "an", "moreover",
                      "furthermore", "finally", "results", "using", "overall", "to", "for", "as", "they"}


def split_sentences(text: str) -> list[str]:
    text = normalize_whitespace(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])", text)
    out: list[str] = []
    for part in parts:
        first = re.split(r"\W", part, maxsplit=1)[0].lower()
        if out and (_ABBREV.search(out[-1]) or
                    (_COUNTRY_ABBREV.search(out[-1]) and first not in _SENTENCE_STARTERS)):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return [s.strip() for s in out if s.strip()]


def split_paragraphs(text: str) -> list[str]:
    return [normalize_whitespace(p) for p in re.split(r"\n\s*\n", text or "") if p.strip()]


@dataclass
class SourceClaim:
    text: str
    locator: str = ""  # e.g. "abstract, sentence 2"


@dataclass
class Interpretation:
    text: str
    basis: str = ""  # what the interpretation rests on


@dataclass
class MemoSection:
    claims: list[SourceClaim] = field(default_factory=list)
    interpretations: list[Interpretation] = field(default_factory=list)


@dataclass
class ResearchMemo:
    paper_id: int | None
    title: str
    analyzer: str
    model: str | None = None
    source_text_kind: str = "abstract"
    sections: dict[str, MemoSection] = field(default_factory=lambda: {k: MemoSection() for k in SECTIONS})
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchMemo":
        d = dict(d)
        d["sections"] = {
            k: MemoSection(
                claims=[SourceClaim(**c) for c in v.get("claims", [])],
                interpretations=[Interpretation(**i) for i in v.get("interpretations", [])],
            ) for k, v in d.get("sections", {}).items()
        }
        return cls(**d)


def _canon(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return normalize_whitespace(text).lower()


def locate(quote: str, source_text: str, kind: str = "abstract") -> str | None:
    """Return a locator if ``quote`` occurs verbatim (modulo whitespace/quotes) in the source."""
    q = _canon(quote).rstrip(".")
    if not q or q not in _canon(source_text):
        return None
    units = split_sentences(source_text) if kind == "abstract" else split_paragraphs(source_text)
    label = "sentence" if kind == "abstract" else "paragraph"
    for i, u in enumerate(units, 1):
        if q in _canon(u):
            return f"{kind.replace('_', ' ')}, {label} {i}"
    return kind.replace("_", " ")


def validate_memo(memo: ResearchMemo, source_text: str) -> ResearchMemo:
    """Drop any claim not verbatim-supported by ``source_text``; record a warning."""
    for key, section in memo.sections.items():
        kept = []
        for c in section.claims:
            loc = locate(c.text, source_text, memo.source_text_kind)
            if loc is None:
                memo.warnings.append(
                    f"Dropped unsupported claim in '{SECTIONS.get(key, key)}': {c.text[:120]!r}")
            else:
                c.locator = loc
                kept.append(c)
        section.claims = kept
    return memo
