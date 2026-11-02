from paper_analyst.analysis import HeuristicAnalyzer
from paper_analyst.memo import (SECTIONS, Interpretation, ResearchMemo, SourceClaim, locate,
                                split_sentences, validate_memo)
from paper_analyst.models import Paper


def test_split_sentences_abbreviations():
    s = split_sentences("We use U.S. data, e.g. CRSP. However, results hold in the U.K. We also test Japan.")
    assert s == ["We use U.S. data, e.g. CRSP.", "However, results hold in the U.K.", "We also test Japan."]


def test_locate_is_whitespace_and_quote_tolerant():
    src = "First sentence.  We find   that it’s large. Last."
    assert locate("We find that it's large.", src) == "abstract, sentence 2"
    assert locate("We find that it is huge.", src) is None


def test_validate_drops_invented_claims():
    memo = ResearchMemo(paper_id=1, title="t", analyzer="x")
    memo.sections["results"].claims = [SourceClaim("We find that pricing errors fall by 10%."),
                                       SourceClaim("Sharpe ratio of 3.5 out of sample.")]
    validate_memo(memo, "We find that pricing errors fall by 10%. Other text.")
    assert [c.text for c in memo.sections["results"].claims] == ["We find that pricing errors fall by 10%."]
    assert memo.sections["results"].claims[0].locator == "abstract, sentence 1"
    assert len(memo.warnings) == 1 and "Sharpe ratio of 3.5" in memo.warnings[0]


def test_heuristic_only_quotes_source(sample_paper):
    memo = HeuristicAnalyzer().analyze(sample_paper)
    assert set(memo.sections) == set(SECTIONS)
    for sec in memo.sections.values():
        for c in sec.claims:
            assert c.text in sample_paper.abstract
            assert c.locator.startswith("abstract, sentence")
    assert memo.sections["research_question"].claims[0].text.startswith("We study whether")
    assert memo.sections["data"].claims[0].text.startswith("Our sample covers")
    assert memo.sections["results"].claims[0].text.startswith("We find")
    assert memo.sections["limitations"].claims[0].text.startswith("However")
    assert memo.warnings == []


def test_heuristic_interpretations_are_labelled(sample_paper):
    memo = HeuristicAnalyzer().analyze(sample_paper)
    interps = [i for s in memo.sections.values() for i in s.interpretations]
    assert interps and all(isinstance(i, Interpretation) and i.basis for i in interps)


def test_heuristic_empty_abstract():
    memo = HeuristicAnalyzer().analyze(Paper(title="No abstract"))
    assert all(not s.claims for s in memo.sections.values())
    assert memo.warnings


def test_heuristic_full_text_mode(sample_paper):
    text = "Intro paragraph. We study whether X holds.\n\nWe find that Y is large. However, Z."
    memo = HeuristicAnalyzer().analyze(sample_paper, full_text=text)
    assert memo.source_text_kind == "full_text"
    assert memo.sections["results"].claims[0].locator == "full text, paragraph 2"


def test_memo_roundtrip(sample_paper):
    memo = HeuristicAnalyzer().analyze(sample_paper)
    again = ResearchMemo.from_dict(memo.to_dict())
    assert again.to_dict() == memo.to_dict()
