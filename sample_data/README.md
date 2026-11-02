# Sample data

**Everything here is synthetic.** It exists so the pipeline can be exercised offline and tested
against known ground truth. None of it is evidence about markets or about the analyzer's accuracy
on real papers. Do not cite it.

| File | Purpose |
|---|---|
| `demo_paper.pdf` | A two-page, two-column working-paper-style PDF (see below). Used by `paper-analyst demo-fulltext` and the tests |
| `demo_paper.groundtruth.json` | For every paragraph: exact text, style, section and the page reportlab placed it on |
| `sample_fulltext.txt` | A synthetic plain-text "full text" for `analyze --text-file` (MVP memo path) |
| `../src/paper_analyst/mock_data/*` | Mocked OpenAlex, arXiv and Semantic Scholar responses for the offline discovery demo |

`demo_paper.pdf` reproduces the layout features that make real papers hard to extract:

* a full-width title, authors and abstract above a two-column body;
* a running header and page numbers, a footnote, numbered sections and a subsection (5.1);
* a paragraph that continues from page 1 to page 2, past the footnote;
* a table with a caption;
* a reference list and a lettered appendix.

Its content is a plausible *shape* of an asset pricing paper. Its numbers are placeholders, and its
references are explicitly marked "Not a real publication".

Rebuild it with:

```bash
python scripts/build_demo_pdf.py
```

This requires reportlab, from `pip install -e ".[dev]"`. Output is byte-reproducible for a given
reportlab version.

The discovery mocks contain deliberate duplicates across sources, to exercise DOI, arXiv-id and
title deduplication. Rebuild them with `python scripts/build_mock_data.py`.
