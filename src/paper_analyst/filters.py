"""Search queries and local (post-fetch) filtering.

Each source translates as much of the query as its API supports; the same
filters are then re-applied locally so results are consistent across sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Paper
from .normalize import normalize_title

# Research-topic presets expand to keyword lists.
TOPIC_PRESETS: dict[str, list[str]] = {
    "international_asset_pricing": ["international asset pricing", "global equity", "cross-country", "international stock returns"],
    "sdf": ["stochastic discount factor", "pricing kernel", "SDF"],
    "return_predictability": ["return predictability", "predictability of returns", "equity premium forecast"],
    "transfer_learning": ["transfer learning", "domain adaptation", "pre-trained"],
    "machine_learning": ["machine learning", "neural network", "deep learning"],
}


@dataclass
class SearchQuery:
    keywords: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    date_from: str | None = None  # "YYYY-MM-DD" or "YYYY"
    date_to: str | None = None
    topics: list[str] = field(default_factory=list)  # keys of TOPIC_PRESETS or free text
    limit: int = 25
    match_all_keywords: bool = False

    def search_terms(self) -> list[str]:
        terms = list(self.keywords)
        for t in self.topics:
            terms.extend(TOPIC_PRESETS.get(t, [t.replace("_", " ")]))
        seen, out = set(), []
        for t in terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out

    def text_query(self) -> str:
        """A plain-text query string for APIs with free-text search."""
        return " ".join(self.keywords) if self.keywords else " ".join(self.search_terms()[:3])


def _date_key(value: str | None, end: bool = False) -> str | None:
    if not value:
        return None
    if len(value) == 4:
        return f"{value}-12-31" if end else f"{value}-01-01"
    if len(value) == 7:
        return f"{value}-31" if end else f"{value}-01"
    return value[:10]


def _author_matches(wanted: str, authors: list[str]) -> bool:
    w = normalize_title(wanted).split()
    if not w:
        return True
    for a in authors:
        tokens = normalize_title(a).split()
        # surname must match; given names may be initials
        if w[-1] in tokens and all(any(t.startswith(x[0]) for t in tokens) for x in w[:-1]):
            return True
    return False


def matches(paper: Paper, query: SearchQuery) -> bool:
    if query.authors and not any(_author_matches(a, paper.authors) for a in query.authors):
        return False
    start, end = _date_key(query.date_from), _date_key(query.date_to, end=True)
    pdate = _date_key(paper.publication_date)
    if (start or end) and not pdate:
        return False
    if start and pdate < start:
        return False
    if end and pdate > end:
        return False
    if query.keywords or query.topics:
        haystack = normalize_title(f"{paper.title} {paper.abstract} {' '.join(paper.topics)}")
        hits = [normalize_title(t) in haystack for t in query.keywords]
        topic_hit = any(normalize_title(t) in haystack for topic in query.topics
                        for t in TOPIC_PRESETS.get(topic, [topic.replace("_", " ")]))
        if query.match_all_keywords:
            if query.keywords and not all(hits):
                return False
            if query.topics and not topic_hit:
                return False
        elif not (any(hits) or topic_hit):
            return False
    return True


def apply_filters(papers: list[Paper], query: SearchQuery) -> list[Paper]:
    return [p for p in papers if matches(p, query)]
