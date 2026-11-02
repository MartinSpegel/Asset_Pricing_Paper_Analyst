from paper_analyst.filters import SearchQuery, apply_filters, matches
from paper_analyst.models import Paper

P = Paper(title="Deep Pricing Kernels", authors=["Laura Becker", "R. Iyer"],
          abstract="A stochastic discount factor estimated by neural networks.", publication_date="2022-11-20")


def test_author_filter_handles_initials():
    assert matches(P, SearchQuery(authors=["Rahul Iyer"]))
    assert matches(P, SearchQuery(authors=["Becker"]))
    assert not matches(P, SearchQuery(authors=["Ada Lindqvist"]))


def test_date_filter():
    assert matches(P, SearchQuery(date_from="2022", date_to="2022"))
    assert not matches(P, SearchQuery(date_from="2023"))
    assert not matches(P, SearchQuery(date_to="2022-06"))
    assert not matches(Paper(title="x"), SearchQuery(date_from="2020"))  # undated excluded


def test_keyword_and_topic_filter():
    assert matches(P, SearchQuery(keywords=["stochastic discount factor"]))
    assert matches(P, SearchQuery(topics=["sdf"]))
    assert not matches(P, SearchQuery(topics=["transfer_learning"]))
    assert matches(P, SearchQuery(keywords=["neural networks", "pricing kernels"], match_all_keywords=True))
    assert not matches(P, SearchQuery(keywords=["neural networks", "momentum"], match_all_keywords=True))


def test_search_terms_expand_presets():
    q = SearchQuery(keywords=["SDF"], topics=["sdf"])
    terms = q.search_terms()
    assert "stochastic discount factor" in terms and terms.count("SDF") == 1


def test_apply_filters():
    assert apply_filters([P, Paper(title="Dividends")], SearchQuery(topics=["sdf"])) == [P]
