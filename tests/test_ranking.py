from paper_analyst.models import Paper
from paper_analyst.ranking import rank, score_paper


def test_relevant_paper_scores_higher():
    hi = Paper(title="Transfer learning of stochastic discount factors in international markets",
               abstract="We study return predictability and the pricing kernel across emerging markets "
                        "with neural networks and domain adaptation.")
    lo = Paper(title="Corporate governance and dividends", abstract="Family firms pay dividends.")
    assert score_paper(hi).score > 60
    assert score_paper(lo).score < 5
    ranked = rank([lo, hi])
    assert ranked[0] is hi
    assert hi.relevance_breakdown["topics"]["Transfer learning"]["matched_terms"]


def test_score_bounds_and_breakdown():
    p = Paper(title="SDF " * 50, abstract="pricing kernel " * 50)
    r = score_paper(p)
    assert 0 <= r.score <= 100
    assert set(r.topics) == {"International asset pricing", "Stochastic discount factors",
                             "Return predictability", "Transfer learning", "Machine learning in finance"}


def test_word_boundaries():
    # "sdf" must not match inside another token
    assert score_paper(Paper(title="xsdfy")).topics["Stochastic discount factors"]["matched_terms"] == {}
