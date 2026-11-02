import pytest

from paper_analyst.fulltext import document_from_abstract, document_from_text
from paper_analyst.profile import (ABSENT, GENUINE, SUPERFICIAL, UNVERIFIED, assess_connections, load_profile,
                                   proposed_extensions)

GENUINE_SDF = """1 Introduction
We study the cross-section of stock returns.

2 Methodology
We estimate the stochastic discount factor weights by generalized method of moments.

3 Results
Out-of-sample pricing errors of the estimated SDF are small, and the tangency portfolio performs well.
"""

SUPERFICIAL_SDF = """1 Introduction
Our question is related to the stochastic discount factor literature and to pricing kernels.

2 Data
We use survey data on household spending.

3 Results
Households spend more when incomes rise.

References
A placeholder entry on the stochastic discount factor.
"""


def levels(doc, prof):
    return {c.key: c.level for c in assess_connections(doc, prof)}


def test_default_profile_loads():
    p = load_profile()
    assert {t.key for t in p.themes} == {"international", "sdf", "ml_transfer", "predictability", "identification"}
    assert p.extensions and all(not any(ch.isdigit() for ch in e.idea) for e in p.extensions)


def test_genuine_vs_superficial():
    p = load_profile()
    assert levels(document_from_text(GENUINE_SDF), p)["sdf"] == GENUINE
    sup = assess_connections(document_from_text(SUPERFICIAL_SDF), p)
    sdf = next(c for c in sup if c.key == "sdf")
    assert sdf.level == SUPERFICIAL
    assert set(sdf.mention_sections) == {"introduction", "references"}
    assert sdf.substantive_hits == []
    assert levels(document_from_text(SUPERFICIAL_SDF), p)["ml_transfer"] == ABSENT


def test_references_never_count_as_substantive():
    doc = document_from_text("1 Introduction\nText.\n\nReferences\nWe estimate the SDF by GMM in 40 countries.\n")
    lv = levels(doc, load_profile())
    assert lv["sdf"] in (SUPERFICIAL, ABSENT) and lv["international"] in (SUPERFICIAL, ABSENT)


def test_abstract_only_is_unverified():
    doc = document_from_abstract("t", "We estimate the stochastic discount factor in 30 countries.")
    assert levels(doc, load_profile())["sdf"] == UNVERIFIED


def test_extensions_follow_levels():
    p = load_profile()
    conns = assess_connections(document_from_text(GENUINE_SDF), p)
    ideas = proposed_extensions(conns, p)
    assert any("outside the estimation market" in i for i in ideas)  # sdf genuine, international absent


def test_custom_profile_and_validation(tmp_path):
    good = tmp_path / "p.toml"
    good.write_text('name = "mine"\n[[themes]]\nkey = "x"\nname = "X"\nconcept_terms = ["momentum"]\n'
                    'substantive_patterns = ["momentum (portfolio|strategy)"]\n')
    prof = load_profile(good)
    doc = document_from_text("1 Results\nThe momentum strategy earns returns.\n\n2 Robustness\nThe momentum portfolio holds up.\n")
    assert levels(doc, prof)["x"] == GENUINE
    bad = tmp_path / "bad.toml"
    bad.write_text('name = "b"\n[[themes]]\nkey = "x"\nname = "X"\n[[extensions]]\nrequires = ["nope"]\nidea = "i"\n')
    with pytest.raises(ValueError, match="unknown themes"):
        load_profile(bad)
