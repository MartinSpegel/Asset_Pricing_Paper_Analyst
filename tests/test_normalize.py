from paper_analyst.normalize import normalize_arxiv_id, normalize_doi, normalize_title


def test_doi_normalization():
    assert normalize_doi("https://doi.org/10.1111/JOFI.1234") == "10.1111/jofi.1234"
    assert normalize_doi("doi:10.1/ABC") == "10.1/abc"
    assert normalize_doi("  ") is None
    assert normalize_doi(None) is None


def test_arxiv_normalization():
    assert normalize_arxiv_id("http://arxiv.org/abs/2101.01234v3") == "2101.01234"
    assert normalize_arxiv_id("10.48550/arXiv.2101.01234") == "2101.01234"
    assert normalize_arxiv_id("q-fin/0601001v1") == "q-fin/0601001"
    assert normalize_arxiv_id("not an id") is None


def test_title_normalization():
    a = normalize_title("Deep Pricing Kernels and the Cross-Section of Returns")
    b = normalize_title("deep pricing kernels and the cross section of returns.")
    assert a == b
    assert normalize_title("Café $\\alpha$ Returns") == "cafe returns"
