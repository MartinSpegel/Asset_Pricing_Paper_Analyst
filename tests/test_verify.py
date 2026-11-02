import copy

from paper_analyst.fulltext import document_from_text
from paper_analyst.report import DeepReport, ItemKind, Locator, ReportItem
from paper_analyst.verify import audit_report, find_span, numbers_in, validate_report

DOC_TEXT = """1 Results
We find that pricing errors fall by 14%, with a t-statistic of 2.9. Gains are larger in emerging markets.

2 Robustness
The results are robust to alternative source markets.
"""


def _report(doc, items):
    r = DeepReport(paper_id=1, title="t", analyzer="test", model=None, profile="p", source_type=doc.source_type,
                   source_sha256=doc.sha256, source_path=None, extractor=doc.extractor)
    r.sections["findings"] = items
    return r


def _bid(doc, start):
    return next(b.id for b in doc.blocks if b.text.startswith(start))


def test_find_span_tolerance():
    assert find_span("We find  that it’s large — really.", "we find that it's large - really") is not None
    assert find_span("abc def", "abc xyz") is None


def test_numbers_in():
    assert numbers_in("fell by 14% (t = 2.90), 1,000 firms, -0.5") == {"14", "2.9", "1000", "0.5"}


def test_validate_keeps_verbatim_and_fixes_locators():
    doc = document_from_text(DOC_TEXT)
    bid = _bid(doc, "We find")
    good = ReportItem(ItemKind.EVIDENCE.value, "pricing errors fall by 14%, with a t-statistic of 2.9",
                      [Locator(block_id=bid, page=99, section="WRONG")])
    r = validate_report(_report(doc, [good]), doc)
    loc = r.sections["findings"][0].locators[0]
    assert loc.page is None and loc.section == "§1 Results" and loc.paragraph == 1  # recomputed, not trusted
    assert r.audit["verbatim_verified"] == 1 and r.audit["dropped"] == 0


def test_validate_drops_fabrications():
    doc = document_from_text(DOC_TEXT)
    bid = _bid(doc, "We find")
    rob = _bid(doc, "The results are robust")
    items = [
        ReportItem(ItemKind.EVIDENCE.value, "pricing errors fall by 25% in all markets", [Locator(bid)]),
        ReportItem(ItemKind.AUTHOR_CLAIM.value, "The results are robust to alternative source markets", [Locator(bid)]),
        ReportItem(ItemKind.INTERPRETATION.value, "A 30% improvement is economically large.", [Locator(bid)]),
        ReportItem(ItemKind.INTERPRETATION.value, "Strong results.", []),
        ReportItem(ItemKind.INTERPRETATION.value, "This echoes Smith et al. (2015).", [Locator(bid)]),
        ReportItem(ItemKind.SPECULATION.value, "Extend to 50 countries.", []),
        ReportItem(ItemKind.INTERPRETATION.value, "The 14% gain is sizeable given a t-statistic of 2.9.", [Locator(bid)]),
        ReportItem(ItemKind.INTERPRETATION.value, "No discussion of transaction costs was found.", [], tags=["absence"]),
        ReportItem(ItemKind.AUTHOR_CLAIM.value, "The results are robust to alternative source markets", [Locator(rob)]),
        ReportItem(ItemKind.EVIDENCE.value, "short", [Locator(bid)]),
        ReportItem(ItemKind.EVIDENCE.value, "pricing errors fall by 14%", [Locator("b9999")]),
    ]
    r = validate_report(_report(doc, items), doc)
    kept = [i.text for i in r.sections["findings"]]
    assert kept == ["The 14% gain is sizeable given a t-statistic of 2.9.",
                    "No discussion of transaction costs was found.",
                    "The results are robust to alternative source markets"]
    assert r.audit["dropped"] == 8
    log = " ".join(r.validation_warnings)
    for needle in ("not found verbatim", "['30']", "cites no source", "Smith et al. (2015)", "['50']", "too short"):
        assert needle in log, needle


def test_audit_detects_tampering():
    doc = document_from_text(DOC_TEXT)
    bid = _bid(doc, "We find")
    r = validate_report(_report(doc, [ReportItem(ItemKind.EVIDENCE.value, "pricing errors fall by 14%",
                                                 [Locator(bid)])]), doc)
    assert audit_report(r, doc)["ok"]
    t = copy.deepcopy(r)
    t.sections["findings"][0].text = "pricing errors fall by 41%"
    assert not audit_report(t, doc)["ok"]
    t = copy.deepcopy(r)
    t.sections["findings"][0].locators[0].section = "§9 Elsewhere"
    res = audit_report(t, doc)
    assert not res["ok"] and res["locator_mismatches"] == 1
    other = document_from_text(DOC_TEXT + "\n3 Extra\nMore text here.\n")
    assert any("hash differs" in i for i in audit_report(r, other)["issues"])
