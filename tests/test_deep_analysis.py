"""Deep-report tests. The synthetic demo PDF checks traceability and labelling mechanics;
it is not evidence that the analyzer is scientifically accurate on real papers."""
import re
from pathlib import Path

import pytest

from paper_analyst.analysis.deep_heuristic import DeepHeuristicAnalyzer
from paper_analyst.fulltext import document_from_abstract, extract_pdf
from paper_analyst.report import REPORT_SECTIONS, DeepReport, ItemKind, render_report
from paper_analyst.verify import audit_report, find_span

DEMO = Path(__file__).resolve().parents[1] / "sample_data" / "demo_paper.pdf"


@pytest.fixture(scope="module")
def doc():
    return extract_pdf(DEMO)


@pytest.fixture(scope="module")
def report(doc):
    return DeepHeuristicAnalyzer().analyze(doc, paper_id=1)


def texts(report, key, kind=None):
    return [i.text for i in report.sections[key] if kind is None or i.kind == kind]


def test_all_sections_and_kinds(report):
    assert list(report.sections) == list(REPORT_SECTIONS)
    c = report.counts()
    assert all(c[k.value] > 0 for k in ItemKind)


def test_every_verbatim_item_is_traceable(report, doc):
    for key, it in report.items():
        if it.kind in ("author_claim", "evidence"):
            loc = it.locators[0]
            block = doc.block(loc.block_id)
            span = find_span(block.text, it.text)
            assert span is not None
            assert loc.page == block.pages_for_span(*span)[0]
            assert loc.section and loc.paragraph
            assert doc.section_of(block).kind not in ("references", "front_matter")
    assert audit_report(report, doc)["ok"]


def test_quantitative_findings_are_evidence_with_pages(report):
    ev = {i.text: i for i in report.sections["findings"] if i.kind == "evidence"}
    key = next(t for t in ev if "reduces the root-mean-squared pricing error by 14%" in t)
    assert ev[key].locators[0].page == 2 and ev[key].locators[0].section == "§6 Empirical Results"
    assert any(i for i in ev.values() if "table" in i.tags)


def test_sections_draw_from_matching_document_sections(report):
    kinds = lambda key: {i.locators[0].section_kind for i in report.sections[key] if i.kind in ("author_claim", "evidence")}
    assert kinds("data") == {"data"}
    assert kinds("identification") <= {"methodology", "appendix"}
    assert "robustness" in kinds("robustness")
    assert any("transaction costs" in t for t in texts(report, "robustness"))


def test_design_assessment(report):
    a = texts(report, "assessment", "interpretation")
    assert any("acknowledge that transaction costs" in t for t in a)
    assert any("acknowledge that multiple testing" in t for t in a)
    assert any(t.startswith("Addressed in the paper: out-of-sample") for t in a)
    assert any("suggested rather than causally identified" in t for t in a)


def test_profile_genuine_vs_superficial(report):
    lv = {c["key"]: c["level"] for c in report.connections}
    assert lv["predictability"] == "superficial"
    assert lv["sdf"] == "genuine" and lv["international"] == "genuine"
    imp = texts(report, "implications", "interpretation")
    assert any(t.startswith("Superficial overlap only with 'Cross-country return predictability'") for t in imp)


def test_speculation_contains_no_numbers_and_is_labelled(report):
    spec = [i for i in report.sections["open_questions"] if i.kind == "speculation"]
    assert spec and all(not re.search(r"\d", i.text) for i in spec)
    md = render_report(report)
    assert "> [!question] Speculative research ideas" in md
    assert md.count("## ") >= 10


def test_report_roundtrip(report):
    again = DeepReport.from_dict(report.to_dict())
    assert again.to_dict() == report.to_dict()


def test_abstract_only_report():
    d = document_from_abstract("t", "We study whether SDFs transfer across 20 countries. We find lower pricing errors.")
    r = DeepHeuristicAnalyzer().analyze(d)
    assert any("ABSTRACT ONLY" in w for w in r.extraction_warnings)
    assert {c["level"] for c in r.connections} <= {"unverified", "absent"}
    assert any("absence" in i.tags for i in r.sections["data"])
