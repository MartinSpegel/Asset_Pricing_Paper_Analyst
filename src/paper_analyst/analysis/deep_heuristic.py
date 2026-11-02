"""Offline, deterministic deep analyzer for full papers.

What it does:
* splits every paragraph into sentences that keep their block locator;
* assigns each sentence to at most one report section using the *document
  section type* it comes from (e.g. "Data") plus cue phrases;
* labels quotes as EVIDENCE (they report quantities, samples, design facts or
  table content) or AUTHOR_CLAIM (questions, contributions, interpretations);
* runs a transparent research-design checklist (out-of-sample evaluation,
  look-ahead bias, multiple testing, transaction costs, inference, ...) whose
  results are INTERPRETATIONs citing the passages found - or explicit absence
  findings when nothing was found;
* assesses research-profile connections and proposes profile-based
  SPECULATIONs.

What it cannot do: understand arguments, check math, or judge whether a
result is correct. Everything it outputs is validated by ``verify.validate_report``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..fulltext.model import Block, Document, SectionKind
from ..memo import split_sentences
from ..profile import ABSENT, GENUINE, PARTIAL, SUPERFICIAL, ResearchProfile, assess_connections, \
    load_profile, proposed_extensions
from ..report import DeepReport, ItemKind, Locator, REPORT_SECTIONS, ReportItem
from ..verify import validate_report

K = SectionKind
SKIP_KINDS = {K.REFERENCES.value, K.FRONT_MATTER.value}

# report section -> {document section kind: weight}
KIND_WEIGHTS: dict[str, dict[str, float]] = {
    "research_question": {"abstract": 2.0, "introduction": 2.0},
    "contribution": {"introduction": 1.5, "literature": 2.5, "abstract": 0.5, "conclusion": 0.5},
    "theory": {"theory": 3.0, "introduction": 0.3, "methodology": 0.5},
    "data": {"data": 3.0, "methodology": 0.5, "appendix": 0.5, "abstract": 0.3},
    "identification": {"methodology": 3.0, "appendix": 0.8, "data": 0.3},
    "findings": {"results": 3.0, "abstract": 1.0, "conclusion": 0.5},
    "robustness": {"robustness": 3.0, "results": 0.5, "conclusion": 0.5, "appendix": 0.5},
    "implications": {"conclusion": 2.0, "results": 0.3, "abstract": 0.3},
    "open_questions": {"conclusion": 1.0},
}
CUES: dict[str, list[tuple[str, float]]] = {
    "research_question": [(r"\b(we|this paper|this study) (study|studies|ask|asks|examine|examines|investigate|investigates|explore|explores|test|tests)\b", 3),
                          (r"\b(whether|question|puzzle|motivat\w*|central to|important for|yet)\b", 1)],
    "contribution": [(r"\b(our|main|key) contributions?\b|\bwe contribute\b", 3),
                     (r"\b(literature|prior (work|studies|research)|previous studies|related to|build on|builds on|complement|unlike|differ(s)? from|in contrast to|extend|first to|novel)\b", 1.5)],
    "theory": [(r"\b(mechanism|channel|intuition|hypothes\w+|equilibrium|euler|pricing equation|pricing kernel|stochastic discount factor|sdf|no-arbitrage)\b", 1.5),
               (r"\b(implies|imply|predicts?|if .{0,60} then|so that|because)\b", 1), (r"=", 0.5)],
    "data": [(r"\b(our )?(sample|data(set)?)\s+(consists?|covers?|comprises?|includes?|spans?)\b", 3),
             (r"\b(we (define|construct|measure|obtain|exclude|winsorize|use data)|defined as|measured (as|with|in)|characteristics|variables?)\b", 1.5),
             (r"\b(19|20)\d{2}\b|\b\d+\s+(countries|markets|firms|stocks|characteristics)\b|\b(crsp|compustat|datastream|worldscope|i/b/e/s|optionmetrics|bloomberg|refinitiv)\b", 1)],
    "identification": [(r"\b(identif\w+|exogenous|instrument\w*|endogene\w+|causal)\b", 2.5),
                       (r"\b(we (estimate|train|fit|minimi[sz]e|re-estimate)|estimat\w+|objective|loss|regression|gmm|method of moments|bootstrap|standard errors?|validation|hyperparameters?|out-of-sample|in-sample|rolling|expanding window|fine-tun\w+|pre-train\w+)\b", 1.5)],
    "findings": [(r"\bwe (find|show|document|demonstrate|establish|report)\b", 3),
                 (r"\b(results?|table \d+|figure \d+|significant\w*|t-stat\w*|sharpe|r-?squared|r2|alpha|outperform\w*|reduc\w+|increas\w+|lower\w*|higher|gains?)\b", 1),
                 (r"\d+(\.\d+)?\s*(%|percent|basis points|bps)|\b\d+\.\d+\b", 1)],
    "robustness": [(r"\b(robust\w*|alternative|sensitiv\w+|placebo|subsample|different (source|specification|window))\b", 2),
                   (r"\b(however|limitation\w*|caveat|do(es)? not (account|address|consider|control)|beyond the scope|disappear\w*|weaker|short)\b", 2)],
    "implications": [(r"\b(implication\w*|suggests?|offers?|practical|middle ground|important for|investors?|practitioners?|policy)\b", 2)],
    "open_questions": [(r"\b(future (research|work)|could examine|left for future|open question|further research|extension\w*|remains to be)\b", 3)],
}
MAX_PER_SECTION = {"findings": 6, "data": 5, "identification": 5}
DEFAULT_MAX = 4
THRESHOLD = 2.5

_QUANTITY = re.compile(
    r"\d+(\.\d+)?\s*(%|percent|basis points|bps)|\b\d+\.\d+\b|\b(19|20)\d{2}\b|"
    r"\b\d+\s+(countries|markets|firms|stocks|months|years|characteristics|observations|portfolios|hidden layers)\b|"
    r"\b(t-stat\w*|sharpe ratio|r-?squared|coefficient)\b[^.]{0,40}\d", re.IGNORECASE)


@dataclass
class Sentence:
    text: str
    block: Block
    kind: str  # document section kind


def _sentences(doc: Document) -> list[Sentence]:
    out = []
    for b in doc.blocks:
        if b.kind not in ("paragraph", "footnote"):
            continue
        s = doc.section_of(b)
        kind = s.kind if s else "other"
        if kind in SKIP_KINDS:
            continue
        for sent in split_sentences(b.text):
            if len(sent) >= 30:
                out.append(Sentence(sent, b, kind))
    return out


def _loc(block_id: str) -> Locator:
    return Locator(block_id=block_id)  # page/section filled in by validate_report


_DESIGN_KINDS = {"data", "methodology", "results", "robustness", "appendix"}


def _has_reported_figure(sent: Sentence) -> bool:
    """Quantities, dates, counts - or any digit in a design/results section (citations [n] ignored)."""
    if _QUANTITY.search(sent.text):
        return True
    stripped = re.sub(r"\[\d+(,\s*\d+)*\]", "", sent.text)
    return sent.kind in _DESIGN_KINDS and bool(re.search(r"\d", stripped))


def _locs(block_ids) -> list[Locator]:
    return [_loc(b) for b in dict.fromkeys(block_ids)]  # de-duplicate, keep order


def _verbatim(sent: Sentence) -> ReportItem:
    kind = ItemKind.EVIDENCE if _has_reported_figure(sent) else ItemKind.AUTHOR_CLAIM
    return ReportItem(kind=kind.value, text=sent.text, locators=[_loc(sent.block.id)])


# ---- research-design checklist ------------------------------------------------
@dataclass
class Check:
    key: str
    label: str
    patterns: str
    relevant_if: tuple[str, ...] = ()  # theme keys; empty = always relevant


CHECKS = [
    Check("out_of_sample", "out-of-sample evaluation",
          r"\bout[- ]of[- ]sample\b|\bhold[- ]?out\b|\btest (sample|period)\b|\brolling (window|estimation)\b"),
    Check("validation", "hyperparameter / model selection on a separate validation sample",
          r"\bvalidation (sample|set|period)\b|\bcross[- ]validat\w+\b|\bhyperparameters?\b|\bearly[- ]stopping\b",
          ("ml_transfer",)),
    Check("look_ahead", "look-ahead bias / real-time information",
          r"\blook[- ]ahead\b|\breporting lag\b|\breal[- ]time\b|\bpoint[- ]in[- ]time\b|\bpublication lag\b"),
    Check("inference", "statistical inference (standard errors / test statistics)",
          r"\bstandard errors?\b|\bt-stat\w*\b|\bbootstrap\w*\b|\bnewey[- ]west\b|\bclustered\b|\bp-values?\b|\bconfidence intervals?\b"),
    Check("multiple_testing", "multiple testing / data snooping",
          r"\bmultiple (testing|hypothes\w+|comparisons)\b|\bdata[- ]snooping\b|\bdata[- ]mining\b|\bfalse discover\w*\b|\bp-hacking\b|\bbonferroni\b"),
    Check("transaction_costs", "transaction costs / implementability",
          r"\btransaction costs?\b|\btrading costs?\b|\bturnover\b|\bnet of (fees|costs)\b|\bimplementab\w+\b"),
    Check("benchmarks", "comparison against benchmark models",
          r"\bbenchmarks?\b|\brelative to\b|\bcompared (with|to)\b|\bcapm\b|\bfama[- ]french\b|\bpooled\b"),
    Check("economic_significance", "economic (not only statistical) significance",
          r"\bsharpe ratio\b|\beconomically\b|\bannuali[sz]ed\b|\bcertainty[- ]equivalent\b|\butility gains?\b|\bbasis points\b"),
    Check("sample_filters", "sample filters, survivorship and microcaps",
          r"\bsurvivorship\b|\bdelist\w*\b|\bmicro[- ]?caps?\b|\bpenny stocks?\b|\bexclude\w*\b|\bpercentile of market cap\w*\b|\bwinsori[sz]\w*\b"),
    Check("heterogeneity", "cross-country / cross-market heterogeneity",
          r"\bemerging\b.{0,60}\bdeveloped\b|\bdeveloped\b.{0,60}\bemerging\b|\bcountry[- ]by[- ]country\b|\bheterogene\w+\b|\bacross (countries|markets)\b",
          ("international",)),
]
_NEGATION = re.compile(r"\b(not|no|without|ignore\w*|do not|does not|did not|fail\w* to|beyond the scope|left for future)\b",
                       re.IGNORECASE)
_EXOGENOUS = re.compile(r"\b(instrument(al)? variables?|exogenous (variation|shock)|natural experiment|"
                        r"difference-in-differences|regression discontinuity|placebo)\b", re.IGNORECASE)
_CONSISTENT = re.compile(r"\bconsistent with\b", re.IGNORECASE)


def _design_checks(doc: Document, sentences: list[Sentence], levels: dict[str, str]) -> list[ReportItem]:
    core = [s for s in sentences if s.kind not in ("introduction", "literature", "abstract")]
    items: list[ReportItem] = []
    for c in CHECKS:
        if c.relevant_if and not any(levels.get(k) in (GENUINE, PARTIAL) for k in c.relevant_if):
            continue
        rx = re.compile(c.patterns, re.IGNORECASE)
        hits = [s for s in core if rx.search(s.text)]
        if not hits:
            items.append(ReportItem(
                kind=ItemKind.INTERPRETATION.value, tags=["absence", f"check:{c.key}"],
                text=f"Not found in the extracted text: {c.label}. This should be verified in the full paper; "
                     "it is a gap in what was extracted and analysed, not proof that the authors omit it.",
                basis=f"Pattern search over theory, data, methodology, results, robustness, conclusion and appendix text: {c.patterns}"))
            continue
        acknowledged_gap = [s for s in hits if _NEGATION.search(s.text)]
        if acknowledged_gap and len(acknowledged_gap) == len(hits):
            text = (f"The authors explicitly acknowledge that {c.label} is not (fully) addressed; "
                    "this limits how far the findings can be taken at face value.")
        else:
            text = f"Addressed in the paper: {c.label} (see cited passages)."
        items.append(ReportItem(kind=ItemKind.INTERPRETATION.value, text=text, tags=[f"check:{c.key}"],
                                locators=_locs(s.block.id for s in hits)[:3],
                                basis="Rule-based design checklist; the cited passages contain the matched terms."))
    # Mechanism: identified or merely 'consistent with'?
    consistent = [s for s in sentences if s.kind in ("results", "robustness", "abstract", "conclusion")
                  and _CONSISTENT.search(s.text)]
    exogenous = [s for s in core if _EXOGENOUS.search(s.text)]
    if consistent and not exogenous:
        items.append(ReportItem(
            kind=ItemKind.INTERPRETATION.value, tags=["check:mechanism_identification"],
            text="The economic mechanism is supported by statements that results are 'consistent with' it, and no "
                 "source of exogenous variation (instruments, natural experiments, placebo designs) was found in "
                 "the extracted text. The mechanism is therefore suggested rather than causally identified.",
            locators=_locs(s.block.id for s in consistent)[:3],
            basis="Co-occurrence check: 'consistent with' language present; exogenous-variation patterns absent."))
    elif exogenous:
        items.append(ReportItem(
            kind=ItemKind.INTERPRETATION.value, tags=["check:mechanism_identification"],
            text="The paper uses a design that targets exogenous variation; check whether its exclusion "
                 "restrictions are credible for the asset pricing mechanism claimed.",
            locators=_locs(s.block.id for s in exogenous)[:3], basis="Exogenous-variation patterns found."))
    return items


EXPECTED_KINDS = [k.value for k in (K.ABSTRACT, K.INTRODUCTION, K.THEORY, K.DATA, K.METHODOLOGY, K.RESULTS,
                                     K.ROBUSTNESS, K.CONCLUSION, K.REFERENCES, K.APPENDIX)]


def init_report(doc: Document, profile: ResearchProfile, analyzer: str, model: str | None,
                paper_id: int | None, title: str | None):
    """Report skeleton shared by all deep analyzers: provenance, coverage, profile connections."""
    report = DeepReport(paper_id=paper_id, title=title or doc.title or "Untitled", analyzer=analyzer,
                        model=model, profile=profile.name, source_type=doc.source_type,
                        source_sha256=doc.sha256, source_path=doc.source_path, extractor=doc.extractor,
                        extraction_warnings=list(doc.warnings))
    present = doc.section_kinds_present()
    report.coverage = {"present": present, "missing": [k for k in EXPECTED_KINDS if k not in present]}
    conns = assess_connections(doc, profile)
    report.connections = [{"key": c.key, "name": c.name, "level": c.level, "rationale": c.rationale,
                           "substantive_blocks": [h.block_id for h in c.substantive_hits],
                           "mention_sections": c.mention_sections} for c in conns]
    return report, conns


class DeepHeuristicAnalyzer:
    name = "deep-heuristic"
    model = None

    def __init__(self, profile: ResearchProfile | None = None):
        self.profile = profile or load_profile()

    def analyze(self, doc: Document, paper_id: int | None = None, title: str | None = None) -> DeepReport:
        report, conns = init_report(doc, self.profile, self.name, None, paper_id, title)
        present = report.coverage["present"]
        sentences = _sentences(doc)
        # 1) assign each sentence to its best report section
        assigned: dict[str, list[tuple[float, int, Sentence]]] = {k: [] for k in KIND_WEIGHTS}
        for idx, s in enumerate(sentences):
            scores = {}
            for key, weights in KIND_WEIGHTS.items():
                cue = sum(w for p, w in CUES[key] if re.search(p, s.text, re.IGNORECASE))
                if cue == 0:
                    continue  # require at least one cue: section membership alone is not enough
                scores[key] = weights.get(s.kind, 0.0) + cue
            if not scores:
                continue
            best = max(scores, key=lambda k: scores[k])
            if scores[best] >= THRESHOLD:
                assigned[best].append((scores[best], idx, s))
        for key, cands in assigned.items():
            top = sorted(cands, key=lambda x: -x[0])[: MAX_PER_SECTION.get(key, DEFAULT_MAX)]
            report.sections[key] = [_verbatim(s) for _, _, s in sorted(top, key=lambda x: x[1])]

        # 2) tables and captions from results/appendix are evidence
        for b in doc.blocks:
            sec = doc.section_of(b)
            if b.kind in ("caption", "table") and sec and sec.kind in ("results", "robustness", "appendix", "data"):
                target = "findings" if sec.kind in ("results", "appendix") else sec.kind
                target = target if target in report.sections else "findings"
                report.sections[target].append(ReportItem(kind=ItemKind.EVIDENCE.value, text=b.text,
                                                          locators=[_loc(b.id)], tags=[b.kind]))

        # 3) note missing dedicated sections
        section_need = {"theory": "theory", "data": "data", "identification": "methodology",
                        "findings": "results", "robustness": "robustness"}
        for rkey, kind in section_need.items():
            if kind not in present:
                report.sections[rkey].insert(0, ReportItem(
                    kind=ItemKind.INTERPRETATION.value, tags=["absence", "coverage"],
                    text=f"No dedicated '{kind}' section was detected from the headings; items here (if any) "
                         "come from other sections and coverage may be incomplete.",
                    basis="Section detection on extracted headings."))

        # 4) research profile connections
        levels = {c.key: c.level for c in conns}
        for c in conns:
            if c.level in (GENUINE, PARTIAL):
                kinds = sorted({h.section_kind for h in c.substantive_hits})
                report.sections["implications"].append(ReportItem(
                    kind=ItemKind.INTERPRETATION.value, tags=["profile", c.level],
                    text=f"{c.level.capitalize()} connection to your agenda theme '{c.name}': the paper works on "
                         f"it in its {', '.join(kinds)} section(s), not only in passing.",
                    locators=_locs(h.block_id for h in c.substantive_hits)[:3],
                    basis="Research-profile assessment (substantive patterns in core sections)."))
            elif c.level == SUPERFICIAL:
                report.sections["implications"].append(ReportItem(
                    kind=ItemKind.INTERPRETATION.value, tags=["profile", c.level],
                    text=f"Superficial overlap only with '{c.name}': the topic is mentioned "
                         f"(in {', '.join(sorted(c.mention_sections))}) but not analysed in the paper's core sections. "
                         "Do not treat this paper as evidence on this theme.",
                    locators=_locs(c.mention_blocks)[:3],
                    basis="Research-profile assessment (concept terms without substantive patterns in core sections)."))
        if doc.source_type == "abstract":
            report.sections["implications"].append(ReportItem(
                kind=ItemKind.INTERPRETATION.value, tags=["absence", "profile"],
                text="Only the abstract is available, so genuine engagement cannot be distinguished from keyword overlap.",
                basis="Source type is abstract."))

        # 5) design assessment
        report.sections["assessment"].extend(_design_checks(doc, sentences, levels))

        # 6) open questions: profile-driven speculation
        support = [h.block_id for c in conns if c.level in (GENUINE, PARTIAL) for h in c.substantive_hits[:1]]
        for idea in proposed_extensions(conns, self.profile):
            report.sections["open_questions"].append(ReportItem(
                kind=ItemKind.SPECULATION.value, text=idea, tags=["profile"],
                locators=_locs(support)[:3],
                basis="Research-profile extension template triggered by this paper's connection pattern "
                      f"({', '.join(f'{k}={v}' for k, v in levels.items())})."))
        for c in conns:
            if c.level == GENUINE:
                for q in self.profile.theme(c.key).questions[:1]:
                    report.sections["open_questions"].append(ReportItem(
                        kind=ItemKind.SPECULATION.value, text=f"Question from your research profile this paper may inform: {q}",
                        tags=["profile"], locators=[_loc(h.block_id) for h in c.substantive_hits[:1]],
                        basis=f"Theme '{c.name}' assessed as genuine."))
        return validate_report(report, doc)
