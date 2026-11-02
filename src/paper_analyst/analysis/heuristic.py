"""Offline, deterministic, extractive analyzer.

It never generates findings: each section is populated only with sentences
copied verbatim from the source text, selected by cue phrases. Interpretations
are limited to transparent, rule-based notes (e.g. agenda relevance from the
ranking) and are explicitly labelled.
"""
from __future__ import annotations

import re

from ..memo import Interpretation, ResearchMemo, SourceClaim, split_paragraphs, split_sentences, validate_memo
from ..models import Paper
from ..ranking import score_paper

# (pattern, weight). Each sentence is assigned to its single best-scoring section;
# ties are broken by the order of this dict.
CUES: dict[str, list[tuple[str, float]]] = {
    "research_question": [(r"\bwe (study|examine|investigate|ask|explore|analy[sz]e|revisit|test)\b", 3),
                          (r"\bthis (paper|article|study) (studies|examines|investigates|asks|explores)\b", 3),
                          (r"\bwhether\b", 1.5), (r"\bquestion\b", 1)],
    "results": [(r"\bwe (find|show|document|demonstrate|establish|report)\b", 3), (r"\bresults? (show|indicate)\b", 2),
                (r"\boutperform", 1.5), (r"\bsignificant", 1), (r"\bsharpe\b", 1),
                (r"\br(\^?2|-squared| squared)\b", 1), (r"\bimprov", 0.5), (r"\bevidence\b", 1),
                (r"\b(reduces?|increases?|deliver|earns?|explains?)\b", 1)],
    "data": [(r"\b(our |the )?(data(set)?|sample) (covers?|consists?|comprises?|includes?)\b", 3),
             (r"\b(using|on) (a )?(panel|sample|data)\b", 2), (r"\b(from|between) (19|20)\d{2} (to|and) (19|20)\d{2}\b", 2),
             (r"\b\d+ (international |developed |emerging )?(countries|markets|stocks|firms|equity markets)\b", 1.5),
             (r"\b(crsp|compustat|datastream|ibes|optionmetrics)\b", 2), (r"\bdata\b", 0.5)],
    "methodology": [(r"\bwe (propose|develop|use|employ|estimate|train|introduce|construct|apply|compare|fine-tune)\b", 2.5),
                    (r"\b(model|framework|approach|estimator|algorithm|architecture|objective)\b", 1),
                    (r"\b(neural network|transfer learning|regression|autoencoder|method of moments|gmm|bootstrap|fine-tun|elastic net|random forest)", 1)],
    "economic_mechanism": [(r"\bmechanism\b", 3), (r"\bchannel\b", 3), (r"\bdriven by\b", 2), (r"\bbecause\b", 1.5),
                           (r"\bconsistent with\b", 2.5), (r"\bcompensat", 1.5), (r"\bmispricing\b", 1.5),
                           (r"\b(frictions?|segmentation|integration|limits to arbitrage|information diffusion)\b", 1.5)],
    "limitations": [(r"\bhowever\b", 2.5), (r"\blimitation", 3), (r"\bcaveat", 3), (r"\bfuture (research|work)\b", 3),
                    (r"\bweaker\b", 1.5), (r"\bnot robust\b", 2), (r"\bsensitive to\b", 1.5), (r"\bdisappear", 1.5),
                    (r"\bcomputationally\b", 1)],
    "research_implications": [(r"\bimplications?\b", 3), (r"\b(results|findings) (suggest|highlight|imply)", 3),
                              (r"\bpractical\b", 1.5), (r"\b(practitioners?|investors?|policy)\b", 1),
                              (r"\bhighlight", 1.5), (r"\bsuggests?\b", 1)],
}

METHOD_TAGS = {
    "transfer learning": r"transfer learning|domain adaptation|fine-tun|pre-?trained",
    "neural networks": r"neural network|deep learning|autoencoder|transformer",
    "tree ensembles": r"random forest|gradient boost|boosted trees",
    "regularised regression": r"lasso|ridge|elastic net|shrinkage",
    "SDF / GMM estimation": r"stochastic discount factor|pricing kernel|\bgmm\b|hansen.jagannathan",
    "predictive regressions": r"predictive regression|out-of-sample r",
    "portfolio sorts": r"portfolio sort|long-short|decile",
}

MAX_PER_SECTION = 3


class HeuristicAnalyzer:
    name = "heuristic"
    model = None

    def analyze(self, paper: Paper, full_text: str | None = None) -> ResearchMemo:
        kind = "full_text" if full_text else "abstract"
        source = full_text or paper.abstract or ""
        memo = ResearchMemo(paper_id=paper.id, title=paper.title, analyzer=self.name, source_text_kind=kind)
        units = split_paragraphs(source) if full_text else split_sentences(source)
        # In full-text mode, quote sentences but search paragraph-by-paragraph.
        sentences = [s for u in units for s in split_sentences(u)] if full_text else units

        if not source.strip():
            memo.warnings.append("No abstract or source text available; memo contains no source-supported claims.")
        for s in sentences:
            scores = {k: sum(w for p, w in pats if re.search(p, s, re.IGNORECASE)) for k, pats in CUES.items()}
            best = max(scores, key=lambda k: scores[k])  # dict order breaks ties
            if scores[best] >= 1 and len(memo.sections[best].claims) < MAX_PER_SECTION:
                memo.sections[best].claims.append(SourceClaim(text=s))

        # ---- clearly labelled, rule-based interpretations ----------------
        tags = [t for t, rx in METHOD_TAGS.items() if re.search(rx, source, re.IGNORECASE)]
        if tags:
            memo.sections["methodology"].interpretations.append(Interpretation(
                text="Method families detected: " + ", ".join(tags) + ".",
                basis="Keyword match on source text; not verified against the paper."))
        if kind == "abstract":
            memo.sections["limitations"].interpretations.append(Interpretation(
                text="This memo is based on the abstract only; robustness, sample details and "
                     "limitations must be checked in the full text.",
                basis="Scope of the available source text."))
        rel = score_paper(paper)
        active = sorted(((n, d) for n, d in rel.topics.items() if d["score"] >= 25),
                        key=lambda x: -x[1]["score"])
        if active:
            memo.sections["research_implications"].interpretations.append(Interpretation(
                text="Relevant to agenda topics: " + "; ".join(
                    f"{n} ({d['score']:.0f}/100, terms: {', '.join(list(d['matched_terms'])[:4])})"
                    for n, d in active) + f". Overall relevance {rel.score:.0f}/100.",
                basis="Keyword-based relevance ranking (paper_analyst.ranking)."))
        return validate_memo(memo, source)
