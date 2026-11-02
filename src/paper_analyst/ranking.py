"""Transparent keyword-based relevance ranking for the research agenda.

Score = sum over topics of (topic weight x saturating match strength), scaled
to 0-100. Title matches count double. Every score carries a breakdown listing
the matched terms so the ranking is auditable.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .models import Paper
from .normalize import normalize_title


@dataclass
class Topic:
    name: str
    weight: float
    terms: dict[str, float]  # term -> term weight


DEFAULT_TOPICS: list[Topic] = [
    Topic("International asset pricing", 1.0, {
        "international asset pricing": 3, "international": 1, "global": 1, "cross country": 2,
        "country level": 1.5, "emerging markets": 1.5, "developed markets": 1.5, "currency": 1,
        "exchange rate": 1, "integration": 1, "home bias": 1.5, "international stock": 2,
    }),
    Topic("Stochastic discount factors", 1.0, {
        "stochastic discount factor": 3, "pricing kernel": 3, "sdf": 2.5, "discount factor": 1.5,
        "no arbitrage": 1.5, "hansen jagannathan": 2, "factor model": 1, "risk premia": 1,
        "risk premium": 1, "asset pricing": 1, "cross section of expected returns": 1.5,
        "anomalies": 1, "pricing errors": 1,
    }),
    Topic("Return predictability", 1.0, {
        "return predictability": 3, "predictability": 2, "out of sample": 1.5, "forecast": 1,
        "equity premium": 2, "predictive regression": 2, "r squared": 1, "r2": 1,
        "predict": 1, "expected returns": 1.5, "market timing": 1.5,
    }),
    Topic("Transfer learning", 1.0, {
        "transfer learning": 3, "domain adaptation": 2.5, "domain adapted": 2.5, "pre trained": 1.5, "pretrained": 1.5,
        "fine tuning": 1.5, "fine tuned": 1.5, "knowledge transfer": 2, "source market": 1.5,
        "target market": 1.5, "multi task": 1, "foundation model": 1.5,
    }),
    Topic("Machine learning in finance", 0.8, {
        "machine learning": 2.5, "deep learning": 2, "neural network": 2, "random forest": 1.5,
        "gradient boosting": 1.5, "autoencoder": 1.5, "lasso": 1, "regularization": 1,
        "nonlinear": 1, "large language model": 1.5, "transformer": 1, "ensemble": 1,
    }),
]

SATURATION = 4.0  # match strength at which a topic is ~63% saturated


@dataclass
class RelevanceResult:
    score: float
    topics: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"score": self.score, "topics": self.topics}


def _count(term: str, text: str) -> int:
    return len(re.findall(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))


def score_paper(paper: Paper, topics: list[Topic] | None = None) -> RelevanceResult:
    topics = topics or DEFAULT_TOPICS
    title = normalize_title(paper.title)
    body = normalize_title(f"{paper.abstract} {' '.join(paper.topics)}")
    total_weight = sum(t.weight for t in topics)
    agg, details = 0.0, {}
    for topic in topics:
        raw, matched = 0.0, {}
        for term, w in topic.terms.items():
            nt = normalize_title(term)
            n_title, n_body = _count(nt, title), min(_count(nt, body), 3)
            if n_title or n_body:
                raw += w * (2 * min(n_title, 1) + n_body)
                matched[term] = n_title + n_body
        strength = 1 - math.exp(-raw / SATURATION)
        agg += topic.weight * strength
        details[topic.name] = {"score": round(100 * strength, 1), "matched_terms": matched}
    score = round(100 * agg / total_weight, 1) if total_weight else 0.0
    # Reward papers spanning several agenda topics (the user's niche is the intersection).
    n_active = sum(1 for d in details.values() if d["score"] >= 25)
    if n_active >= 3:
        score = min(100.0, round(score * 1.15, 1))
    return RelevanceResult(score=score, topics=details)


def rank(papers: list[Paper], topics: list[Topic] | None = None) -> list[Paper]:
    for p in papers:
        r = score_paper(p, topics)
        p.relevance_score, p.relevance_breakdown = r.score, r.to_dict()
    return sorted(papers, key=lambda p: (p.relevance_score or 0), reverse=True)
