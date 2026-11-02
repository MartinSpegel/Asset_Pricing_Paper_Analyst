from paper_analyst.filters import SearchQuery
from paper_analyst.sources import ArxivSource, OpenAlexSource, SemanticScholarSource
from paper_analyst.sources.openalex import reconstruct_abstract


def test_reconstruct_abstract():
    assert reconstruct_abstract({"b": [1], "a": [0, 2]}) == "a b a"
    assert reconstruct_abstract(None) == ""


def test_openalex_parse(transport):
    papers = OpenAlexSource(transport).search(SearchQuery(keywords=["asset pricing"]))
    assert len(papers) == 4
    p = papers[0]
    assert p.doi == "10.5555/apa-demo.0001"
    assert p.arxiv_id == "9901.00001"  # recovered from an arXiv location
    assert p.abstract.startswith("We study whether information")
    assert p.authors == ["Ada Lindqvist", "Tomas Herrera"]
    assert p.sources == ["openalex"]


def test_openalex_params_with_author_and_dates(transport):
    src = OpenAlexSource(transport, mailto="me@example.org")
    q = SearchQuery(keywords=["pricing kernel"], authors=["Ada Lindqvist"], date_from="2020", date_to="2024-06")
    src.search(q)
    (s1, _, p1), (s2, _, p2) = transport.calls
    assert s1 == "openalex_authors" and p1["search"] == "Ada Lindqvist"
    assert s2 == "openalex"
    assert "from_publication_date:2020-01-01" in p2["filter"]
    assert "to_publication_date:2024-06-31" in p2["filter"]
    assert "authorships.author.id:A500000000" in p2["filter"]
    assert p2["mailto"] == "me@example.org"


def test_arxiv_parse_and_query(transport):
    src = ArxivSource(transport)
    q = SearchQuery(keywords=["transfer learning", "SDF"], authors=["Lindqvist"], date_from="2020-01-01")
    papers = src.search(q)
    assert [p.arxiv_id for p in papers] == ["9901.00001", "9901.00003", "9901.00004"]
    assert papers[0].doi == "10.5555/apa-demo.0001"
    assert papers[0].urls["pdf"].endswith("9901.00001v2")
    sq = transport.calls[0][2]["search_query"]
    assert 'all:"transfer learning" OR all:SDF' in sq
    assert "au:Lindqvist" in sq
    assert "submittedDate:[202001010000 TO 20991231" in sq
    assert "cat:q-fin.*" in sq


def test_semantic_scholar_parse(transport):
    src = SemanticScholarSource(transport, api_key="dummy")
    papers = src.search(SearchQuery(keywords=["x"], date_from="2019", date_to="2024"))
    assert len(papers) == 5
    assert papers[0].doi == "10.5555/apa-demo.0001" and papers[0].arxiv_id == "9901.00001"
    assert papers[1].abstract == ""  # S2 sometimes lacks abstracts
    params = transport.calls[0][2]
    assert params["publicationDateOrYear"] == "2019-01-01:2024-12-31"
