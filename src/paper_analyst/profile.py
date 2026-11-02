"""Configurable research profile and paper-to-agenda connection assessment.

The assessment deliberately separates *genuine* research connections from
*superficial keyword overlap*:

* concept mentions are counted everywhere (including introduction, literature
  review and references) but on their own only establish "superficial" overlap;
* substantive patterns (estimating an SDF, using country panels, training and
  validating a model, identification strategies ...) are counted only in the
  paper's core sections; only they can establish a "partial" or "genuine"
  connection.

Every hit carries a block locator, so the classification is auditable.
"""
from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

from .fulltext.model import CORE_KINDS, Document

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

GENUINE, PARTIAL, SUPERFICIAL, ABSENT, UNVERIFIED = "genuine", "partial", "superficial", "absent", "unverified"
_CORE = {k.value for k in CORE_KINDS}


@dataclass
class Theme:
    key: str
    name: str
    concept_terms: list[str]
    substantive_patterns: list[str]
    questions: list[str] = field(default_factory=list)

    def compiled(self) -> list[re.Pattern]:
        return [re.compile(p, re.IGNORECASE) for p in self.substantive_patterns]


@dataclass
class Extension:
    requires: list[str]
    lacks: list[str]
    idea: str


@dataclass
class ResearchProfile:
    name: str
    description: str
    themes: list[Theme]
    extensions: list[Extension] = field(default_factory=list)
    genuine_min_core_kinds: int = 2
    genuine_min_core_hits: int = 3
    partial_min_core_hits: int = 1
    source: str = ""

    def theme(self, key: str) -> Theme:
        return next(t for t in self.themes if t.key == key)


def load_profile(path: str | Path | None = None) -> ResearchProfile:
    if path is None:
        text = resources.files("paper_analyst.profiles").joinpath("default.toml").read_text(encoding="utf-8")
        source = "default.toml (bundled)"
    else:
        text, source = Path(path).read_text(encoding="utf-8"), str(path)
    data = tomllib.loads(text)
    a = data.get("assessment", {})
    themes = [Theme(key=t["key"], name=t["name"], concept_terms=t.get("concept_terms", []),
                    substantive_patterns=t.get("substantive_patterns", []), questions=t.get("questions", []))
              for t in data.get("themes", [])]
    keys = {t.key for t in themes}
    exts = [Extension(requires=e.get("requires", []), lacks=e.get("lacks", []), idea=e["idea"])
            for e in data.get("extensions", [])]
    for e in exts:
        unknown = (set(e.requires) | set(e.lacks)) - keys
        if unknown:
            raise ValueError(f"Profile extension references unknown themes: {sorted(unknown)}")
    for t in themes:
        t.compiled()  # validate regexes early
    return ResearchProfile(name=data.get("name", "unnamed"), description=data.get("description", "").strip(),
                           themes=themes, extensions=exts,
                           genuine_min_core_kinds=a.get("genuine_min_core_kinds", 2),
                           genuine_min_core_hits=a.get("genuine_min_core_hits", 3),
                           partial_min_core_hits=a.get("partial_min_core_hits", 1), source=source)


@dataclass
class Hit:
    block_id: str
    section_kind: str
    match: str


@dataclass
class ThemeConnection:
    key: str
    name: str
    level: str                            # genuine | partial | superficial | absent | unverified
    rationale: str
    mention_sections: dict[str, int] = field(default_factory=dict)   # section kind -> concept mentions
    substantive_hits: list[Hit] = field(default_factory=list)        # core-section hits only
    noncore_substantive_hits: list[Hit] = field(default_factory=list)
    mention_blocks: list[str] = field(default_factory=list)          # blocks with concept mentions

    def to_dict(self) -> dict:
        return asdict(self)


def _count_terms(text: str, terms: list[str]) -> int:
    t = text.lower()
    return sum(len(re.findall(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", t)) for term in terms)


def assess_connections(doc: Document, profile: ResearchProfile) -> list[ThemeConnection]:
    sectioned = doc.source_type != "abstract" and any(s.heading_block for s in doc.sections)
    out = []
    for theme in profile.themes:
        pats = theme.compiled()
        mentions: dict[str, int] = {}
        mention_blocks: list[str] = []
        core_hits, other_hits = [], []
        for b in doc.blocks:
            if b.kind in ("heading", "title"):
                continue
            s = doc.section_of(b)
            kind = s.kind if s else "other"
            n = _count_terms(b.text, theme.concept_terms)
            if n:
                mentions[kind] = mentions.get(kind, 0) + n
                mention_blocks.append(b.id)
            if kind == "references":
                continue  # reference titles never count as substantive engagement
            for p in pats:
                m = p.search(b.text)
                if m:
                    (core_hits if kind in _CORE else other_hits).append(Hit(b.id, kind, m.group(0)[:80]))
                    break
        total_mentions = sum(mentions.values())
        core_kinds = {h.section_kind for h in core_hits}
        mr_hits = sum(1 for h in core_hits if h.section_kind in ("methodology", "results"))
        if not sectioned:
            level = UNVERIFIED if (total_mentions or other_hits or core_hits) else ABSENT
            why = ("Full text with section structure is required to separate genuine engagement from keyword "
                   f"overlap; found {total_mentions} concept mention(s) and {len(other_hits) + len(core_hits)} "
                   "substantive-pattern match(es) in unsectioned text.")
        elif len(core_kinds) >= profile.genuine_min_core_kinds or mr_hits >= profile.genuine_min_core_hits:
            level = GENUINE
            why = (f"Substantive engagement in core sections ({', '.join(sorted(core_kinds))}): "
                   f"{len(core_hits)} matching paragraph(s).")
        elif len(core_hits) >= profile.partial_min_core_hits:
            level = PARTIAL
            why = f"Some substantive engagement, limited to {', '.join(sorted(core_kinds))} ({len(core_hits)} paragraph(s))."
        elif total_mentions or other_hits:
            level = SUPERFICIAL
            where = ", ".join(f"{k} ({v})" for k, v in sorted(mentions.items())) or "non-core sections"
            only_refs = set(mentions) == {"references"}
            why = ("Keyword overlap only" + (" (reference list only)" if only_refs else "") +
                   f": concept terms appear in {where}, but no substantive use was found in the paper's "
                   "theory, data, methodology, results or robustness sections.")
        else:
            level, why = ABSENT, "No concept terms or substantive patterns found."
        out.append(ThemeConnection(theme.key, theme.name, level, why, mentions, core_hits, other_hits, mention_blocks))
    return out


def proposed_extensions(connections: list[ThemeConnection], profile: ResearchProfile) -> list[str]:
    lv = {c.key: c.level for c in connections}
    strong = {GENUINE, PARTIAL}
    weak = {SUPERFICIAL, ABSENT}
    return [e.idea for e in profile.extensions
            if all(lv.get(k) in strong for k in e.requires) and all(lv.get(k) in weak for k in e.lacks)]
