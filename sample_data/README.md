# Sample data

Everything here and in `src/paper_analyst/mock_data/` is **synthetic**. The papers, authors,
DOIs (prefix `10.5555`, reserved for testing) and arXiv ids (`9901.xxxxx`) are made up so the
pipeline can be exercised offline. Do not cite them.

| File | Purpose |
|---|---|
| `../src/paper_analyst/mock_data/openalex_works.json` | Mocked OpenAlex `/works` response (abstracts as `abstract_inverted_index`) |
| `../src/paper_analyst/mock_data/openalex_authors.json` | Mocked OpenAlex `/authors` lookup |
| `../src/paper_analyst/mock_data/arxiv_query.xml` | Mocked arXiv Atom feed |
| `../src/paper_analyst/mock_data/semantic_scholar_search.json` | Mocked Semantic Scholar `/paper/search` response |
| `sample_fulltext.txt` | Synthetic "full text" for demo paper 1, for `analyze --text-file` |

The mock corpus has deliberate overlaps to show deduplication:

* Paper 1 appears in all three sources. The DOI is upper-case in Semantic Scholar, and the arXiv
  id is also attached to the OpenAlex record.
* Paper 2 appears in OpenAlex and in Semantic Scholar. The Semantic Scholar record has a
  `https://doi.org/...` DOI and no abstract.
* Paper 3 appears in arXiv and in Semantic Scholar with no ids at all. It only matches on the
  normalised title.
* Some papers are filtered out: an off-topic corporate-finance paper, and a 2016 paper that
  falls outside the demo's `--from 2018` window.

Regenerate the mocks with `python scripts/build_mock_data.py`.
