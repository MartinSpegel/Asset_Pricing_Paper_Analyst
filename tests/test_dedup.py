from paper_analyst.dedup import deduplicate
from paper_analyst.filters import apply_filters
from paper_analyst.models import Paper
from paper_analyst.sources import ALL_SOURCES


def test_dedup_by_doi_arxiv_and_title():
    a = Paper(title="A Long Enough Paper Title Here", doi="10.1/X", sources=["openalex"], venue="J. Fin.")
    b = Paper(title="Different Title Same DOI Paper", doi="https://doi.org/10.1/x", arxiv_id="2101.00001",
              abstract="longer abstract", sources=["semantic_scholar"])
    c = Paper(title="Another", arxiv_id="2101.00001v2", sources=["arxiv"], venue="arXiv")
    d = Paper(title="a long-enough paper title, here!", sources=["arxiv"])
    e = Paper(title="Unrelated Paper On Something Else", sources=["arxiv"])
    out = deduplicate([a, b, c, d, e])
    assert len(out) == 2
    m = out[0]
    assert m.doi == "10.1/X" or m.doi == "10.1/x"
    assert m.arxiv_id == "2101.00001"
    assert m.abstract == "longer abstract"
    assert m.venue == "J. Fin."
    assert m.sources == ["arxiv", "openalex", "semantic_scholar"]


def test_bridge_record_merges_two_groups():
    a = Paper(title="First Record With Doi Only", doi="10.1/a", sources=["openalex"])
    b = Paper(title="Second Record With Arxiv Only", arxiv_id="2201.00002", sources=["arxiv"])
    bridge = Paper(title="Bridge", doi="10.1/a", arxiv_id="2201.00002", sources=["semantic_scholar"])
    assert len(deduplicate([a, b, bridge])) == 1


def test_short_titles_not_merged():
    assert len(deduplicate([Paper(title="Comment"), Paper(title="Comment")])) == 2


def test_mock_corpus_dedup(transport, broad_query):
    papers = []
    for cls in ALL_SOURCES.values():
        papers += cls(transport).search(broad_query)
    unique = deduplicate(apply_filters(papers, broad_query))
    titles = {p.title for p in unique}
    # P1 appears in all three sources, P2 in two, P3 in two (title-only match for S2).
    assert sum("Transfer Learning Across Equity Markets" in t for t in titles) == 1
    assert sum("Deep Pricing Kernels" in t.title() for t in titles) == 1
    p1 = next(p for p in unique if p.doi == "10.5555/apa-demo.0001")
    assert set(p1.sources) == {"openalex", "arxiv", "semantic_scholar"}
    assert "Machine Learning for Credit Card Fraud Detection" in titles  # passes the ML topic filter
