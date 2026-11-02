"""Builds the synthetic mock API responses used by the offline demo and tests.

All papers, authors, DOIs (10.5555 is a test prefix) and arXiv ids (99xx.xxxxx)
are FICTIONAL. Run: python scripts/build_mock_data.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "paper_analyst" / "mock_data"

P1 = dict(
    title="Transfer Learning Across Equity Markets: Estimating Stochastic Discount Factors in Data-Scarce Countries",
    authors=["Ada Lindqvist", "Tomas Herrera"], date="2024-03-15", doi="10.5555/apa-demo.0001", arxiv="9901.00001",
    venue="Demo Journal of Financial Econometrics",
    abstract=("We study whether information from the U.S. equity market can improve the estimation of stochastic "
              "discount factors in international markets with short return histories. We propose a transfer learning "
              "approach in which a neural network SDF is pre-trained on U.S. stock returns and fine-tuned on each target "
              "country. Our sample covers monthly returns of stocks in 32 developed and emerging markets from 1990 to 2022. "
              "We find that the transferred SDF reduces out-of-sample pricing errors by 18% relative to a model estimated "
              "on local data only, and the tangency portfolio implied by the SDF achieves an annualized Sharpe ratio of 1.1. "
              "The gains are largest in emerging markets, consistent with the view that partial market integration allows "
              "common risk premia to be learned from a data-rich source market. However, the benefits are weaker for markets "
              "with low integration with the U.S. Our results suggest that transfer learning is a practical tool for "
              "international asset pricing when local data are scarce."))
P2 = dict(
    title="Return Predictability Around the World: A Machine Learning Perspective",
    authors=["Mei Watanabe", "Kofi Mensah", "Ada Lindqvist"], date="2023-06-01", doi="10.5555/apa-demo.0002",
    venue="Demo Review of Asset Pricing Studies",
    abstract=("This paper examines return predictability in 40 international equity markets using machine learning "
              "methods. We compare predictive regressions, elastic net, random forests and neural networks using "
              "country-level and firm-level predictors from 1995 to 2021. Neural networks deliver the highest "
              "out-of-sample R-squared, but predictability varies substantially across countries. We find that "
              "predictability is concentrated in markets with higher limits to arbitrage, which points to mispricing "
              "rather than time-varying risk premia as the main channel. Future research should examine whether "
              "these patterns survive transaction costs."))
P3 = dict(
    title="Deep Pricing Kernels and the Cross-Section of International Stock Returns",
    authors=["Laura Becker", "Rahul Iyer"], date="2022-11-20", arxiv="9901.00003", venue="arXiv",
    abstract=("We estimate a nonlinear pricing kernel for international stock returns with a deep neural network that "
              "enforces the no-arbitrage condition. The model is estimated with a generalized method of moments objective "
              "on a panel of stocks from 23 developed markets. We show that a single global SDF explains a large share of "
              "the cross-section of expected returns in developed markets, while country-specific factors remain important "
              "for Japan. The results highlight the importance of nonlinear interactions between firm characteristics."))
P4 = dict(
    title="Conditional Factor Models with Domain-Adapted Neural Networks",
    authors=["Sofia Rossi", "Tomas Herrera"], date="2025-01-10", arxiv="9901.00004", venue="arXiv",
    abstract=("We introduce a domain adaptation framework for conditional factor models in which an autoencoder "
              "learns latent factors in a source market and adapts them to a target market with a different "
              "distribution of firm characteristics. Using stocks from the United States as source and from Europe "
              "as target between 2000 and 2023, we document that domain-adapted factors reduce pricing errors "
              "relative to factors learned on the target market alone. However, the approach is computationally "
              "intensive and its performance is sensitive to the choice of source market."))
P5 = dict(
    title="Corporate Governance and Dividend Policy in Family Firms",
    authors=["Henrik Dahl"], date="2021-04-02", doi="10.5555/apa-demo.0005", venue="Demo Corporate Finance Letters",
    abstract=("We examine how family control affects dividend payouts using a sample of listed firms. We find that "
              "family firms pay higher dividends when minority shareholder protection is strong."))
P6 = dict(
    title="Out-of-Sample Equity Premium Forecasts and Investor Sentiment",
    authors=["Kofi Mensah"], date="2016-09-01", doi="10.5555/apa-demo.0006", venue="Demo Finance Quarterly",
    abstract=("We investigate whether investor sentiment improves equity premium forecasts. We find modest "
              "out-of-sample gains for return predictability that disappear after 2008."))
P7 = dict(
    title="Large Language Models and Return Predictability from Financial News",
    authors=["Rahul Iyer", "Mei Watanabe"], date="2024-09-30", doi="10.5555/apa-demo.0007",
    venue="Demo Working Paper Series",
    abstract=("We ask whether embeddings from a pre-trained large language model can predict stock returns from news. "
              "We fine-tune the model on headlines for U.S. firms between 2010 and 2023. A long-short portfolio sorted "
              "on model predictions earns significant returns that are not explained by standard factor models. The "
              "predictability is concentrated in small stocks, which suggests slow information diffusion as the mechanism."))
P8 = dict(
    title="Machine Learning for Credit Card Fraud Detection",
    authors=["Jane Placeholder"], date="2023-02-14", doi="10.5555/apa-demo.0008", venue="Demo Applied Computing",
    abstract="We apply gradient boosting to detect fraudulent transactions.")


def inverted(text):
    idx = {}
    for i, w in enumerate(text.split()):
        idx.setdefault(w, []).append(i)
    return idx


def oa_work(p, n, extra_locations=()):
    return {
        "id": f"https://openalex.org/W99000000{n}",
        "doi": f"https://doi.org/{p['doi']}" if p.get("doi") else None,
        "title": p["title"], "display_name": p["title"],
        "publication_date": p["date"], "publication_year": int(p["date"][:4]),
        "ids": {"openalex": f"https://openalex.org/W99000000{n}"},
        "authorships": [{"author": {"id": f"https://openalex.org/A50000000{i}", "display_name": a}}
                        for i, a in enumerate(p["authors"])],
        "primary_location": {"landing_page_url": f"https://doi.org/{p['doi']}" if p.get("doi") else None,
                             "pdf_url": None, "source": {"display_name": p["venue"]}},
        "locations": [{"landing_page_url": u} for u in extra_locations],
        "open_access": {"is_oa": False, "oa_url": None},
        "topics": [{"display_name": "Financial Markets and Investment Strategies"}],
        "abstract_inverted_index": inverted(p["abstract"]),
    }


openalex = {"meta": {"count": 4, "page": 1, "per_page": 25}, "results": [
    oa_work(P1, 1, ["https://arxiv.org/abs/9901.00001"]),
    oa_work(P2, 2), oa_work(P5, 5), oa_work(P7, 7)]}
openalex_authors = {"meta": {"count": 1}, "results": [
    {"id": "https://openalex.org/A500000000", "display_name": "Ada Lindqvist", "works_count": 12}]}


def s2(p, pid, doi=None, arxiv=None, title=None, abstract=True):
    ext = {}
    if doi:
        ext["DOI"] = doi
    if arxiv:
        ext["ArXiv"] = arxiv
    return {"paperId": pid, "title": title or p["title"],
            "abstract": p["abstract"] if abstract else None,
            "authors": [{"authorId": str(i), "name": a} for i, a in enumerate(p["authors"])],
            "year": int(p["date"][:4]), "publicationDate": p["date"], "externalIds": ext,
            "url": f"https://www.semanticscholar.org/paper/{pid}", "venue": p["venue"],
            "openAccessPdf": None, "fieldsOfStudy": ["Economics", "Computer Science"]}


semantic = {"total": 5, "offset": 0, "data": [
    s2(P1, "s2demo0001", doi="10.5555/APA-DEMO.0001", arxiv="9901.00001"),
    s2(P2, "s2demo0002", doi="https://doi.org/10.5555/apa-demo.0002", abstract=False),
    # Same as P3 but different capitalisation/punctuation and no ids -> title dedup
    s2(P3, "s2demo0003", title="Deep pricing kernels and the cross section of international stock returns"),
    s2(P6, "s2demo0006", doi=P6["doi"]),
    s2(P8, "s2demo0008", doi=P8["doi"]),
]}


def atom_entry(p, version="v2", doi=None, cats=("q-fin.PR", "stat.ML")):
    authors = "".join(f"<author><name>{a}</name></author>" for a in p["authors"])
    cat_xml = "".join(f'<category term="{c}" scheme="http://arxiv.org/schemas/atom"/>' for c in cats)
    doi_xml = f"<arxiv:doi>{doi}</arxiv:doi>" if doi else ""
    return f"""  <entry>
    <id>http://arxiv.org/abs/{p['arxiv']}{version}</id>
    <updated>{p['date']}T00:00:00Z</updated>
    <published>{p['date']}T00:00:00Z</published>
    <title>{p['title']}</title>
    <summary>  {p['abstract']}
    </summary>
    {authors}
    {doi_xml}
    <link href="http://arxiv.org/abs/{p['arxiv']}{version}" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/{p['arxiv']}{version}" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="{cats[0]}" scheme="http://arxiv.org/schemas/atom"/>
    {cat_xml}
  </entry>
"""


arxiv = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <title type="html">ArXiv Query: synthetic demo feed</title>
  <opensearch:totalResults>3</opensearch:totalResults>
{atom_entry(P1, doi=P1['doi'])}{atom_entry(P3, version='v1')}{atom_entry(P4, version='v3', cats=('q-fin.ST', 'cs.LG'))}</feed>
"""

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "openalex_works.json").write_text(json.dumps(openalex, indent=1) + "\n")
(OUT / "openalex_authors.json").write_text(json.dumps(openalex_authors, indent=1) + "\n")
(OUT / "semantic_scholar_search.json").write_text(json.dumps(semantic, indent=1) + "\n")
(OUT / "arxiv_query.xml").write_text(arxiv)
print("wrote mock data to", OUT)
