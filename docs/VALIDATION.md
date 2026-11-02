# Validation status

This document states plainly which capabilities are tested, how they are tested, and what still
needs validation before the tool can be trusted on real papers.

> **No real paper was used in development.** The build environment could not reach arXiv,
> SSRN, NBER, OpenAlex or Semantic Scholar. All PDF tests use synthetic documents with **known
> ground truth**. They show that extraction, traceability and labelling *work mechanically*. They
> are **not evidence of scientific accuracy** on real papers. The synthetic demo paper's
> "findings" are placeholders and must never be cited.

## Tested automatically (`pytest`, 95 tests)

| Capability | How it is tested | Test file |
|---|---|---|
| Discovery: API response parsing and query construction (OpenAlex, arXiv, Semantic Scholar) | Mocked responses in each API's documented format; request parameters asserted | `test_sources.py` |
| Filters, deduplication, ranking, SQLite persistence | Unit tests | `test_filters.py`, `test_dedup.py`, `test_ranking.py`, `test_storage.py` |
| PDF extraction: paragraph text, **physical page**, **section** and **reading order** | Every paragraph of the synthetic two-column demo PDF is compared with ground truth that reportlab recorded at layout time | `test_pdf_extraction.py` |
| Two-column reading order, full-width title/abstract inside columns | Ground truth plus a programmatic two-column fixture | `test_pdf_extraction.py` |
| Running headers, footers and page numbers removed; printed page labels kept | Ground truth | `test_pdf_extraction.py` |
| Paragraphs that cross pages, columns and footnotes keep correct per-quote pages | `pages_for_span` assertions | `test_pdf_extraction.py` |
| De-hyphenation, indentation-based paragraph breaks, reference entries, tables, captions | Programmatic fixtures | `test_pdf_extraction.py` |
| Regular-weight / ALL-CAPS roman-numeral headings | Programmatic fixture | `test_pdf_extraction.py` |
| Failure handling: encrypted (with and without password), image-only, partially image-only, corrupt, non-PDF, missing and unsupported files | Programmatic fixtures; explicit `ExtractionError`s or warnings | `test_pdf_extraction.py` |
| Section-kind classification and heading parsing | Unit tests, plain-text documents | `test_sections_text.py` |
| Verbatim verification: fabricated quotes, wrong blocks, invented numbers, invented author-year citations and uncited interpretations are dropped | Adversarial unit tests | `test_verify.py` |
| Locators are recomputed from the document and never trusted from an analyzer | Unit test with a deliberately wrong page and section | `test_verify.py` |
| Audit detects tampered quotes, tampered locators and changed source files | Unit and CLI tests | `test_verify.py`, `test_cli_fulltext.py` |
| Research profile: genuine vs superficial vs absent vs unverified; reference-list mentions never count; custom profiles; profile validation | Constructed documents | `test_profile.py` |
| Deep heuristic report: all 10 sections; every verbatim item traceable to page, section and paragraph; quantitative results labelled as evidence; design checks; speculation has no numbers | Synthetic demo PDF | `test_deep_analysis.py` |
| Claude deep analyzer: request shape, schema, refusal, invalid JSON, fallback flag, validation of model output | Fake streaming client (**no API calls**) | `test_deep_claude.py` |
| CLI workflows: extract, ingest, deep-analyze, audit, profile, demo-fulltext; paid calls require `--yes` | End-to-end on temporary databases | `test_cli_fulltext.py` |
| No API keys in the repository | Pattern scan | `test_no_secrets.py` |

The streaming request was also checked once by hand against the real `anthropic` Python SDK
(v2.3), pointed at a local stub server; no request reached Anthropic. The SDK accepted the request
shape (`output_config` JSON schema, `fallbacks`, beta header, streaming). The validator then
dropped a fabricated quote and an invented percentage returned by the stub.

## Not yet validated (requires real papers)

| Area | Risk | How to validate |
|---|---|---|
| Extraction on real journal and working-paper PDFs: LaTeX, Word, SSRN cover pages, journal templates | Wrong reading order, missed headings, merged or split paragraphs | Run `paper-analyst extract paper.pdf --markdown out.md` and compare with the PDF; see the protocol below |
| Math-heavy text | Equations extract as garbled symbols; quotes that include formulas may fail to verify (they are dropped, not invented) | Inspect sections with equations |
| Tables | Only simple tables with one row per line are recognised. Complex or rotated tables, and tables spanning both columns in a two-column layout, may be mis-ordered | Compare table blocks with the PDF |
| Footnotes inside columns, endnotes, figure-embedded text | Footnotes are recognised only by small font in the lower page area | Spot-check |
| Layouts with three or more columns, rotated pages, landscape tables | Not supported (only one gutter is detected) | Avoid, or check by hand |
| Scanned PDFs | Rejected explicitly; OCR is not performed | Run `ocrmypdf` first |
| Section classification | Keyword-based on headings; unusual titles (e.g. "Why do kernels travel?") map to `other` | Check the `extract` section table |
| Heuristic sentence selection | Cue-based; it can choose a less important sentence or misfile one. It cannot invent text | Expert review of sample reports |
| Evidence vs author-claim labelling | Rule: sentences reporting figures, dates or counts (or containing digits in data/method/results sections) are evidence | Expert review |
| Design checklist | Keyword detection. "Addressed" means the terms occur, not that the treatment is adequate. "Not found" means not found in the extracted text | Expert review |
| Profile connection levels | Regex patterns and thresholds in `profiles/default.toml` | Label 20–30 real papers as genuine or superficial per theme and compare; tune patterns |
| Claude deep analyzer on real papers | Quality, coverage and cost have **never been measured**; no paid request was made | With explicit approval, run on a few papers you know well and grade the reports |

## Protocol for validating on your own papers

1. Pick 5–10 papers you know well, in different layouts: one- and two-column, LaTeX and Word,
   SSRN and journal versions.
2. Check extraction:
   ```bash
   paper-analyst extract paper.pdf --markdown paper.extracted.md
   ```
   Then check: section list and kinds; pages of 10 random paragraphs; that no header or footer
   text is mixed into body text; that two-column pages read left column then right column; that
   the warnings are sensible.
3. Run the analysis and audit:
   ```bash
   paper-analyst ingest paper.pdf
   paper-analyst deep-analyze --id N
   paper-analyst audit --id N
   ```
   The audit must pass. It only proves traceability, not quality.
4. Grade each report section on three questions. Are the most important claims and results
   present? Is anything mislabelled, such as an interpretation shown as a claim? Are the absence
   findings correct?
5. Record failures as test cases. Add an anonymised minimal PDF fixture to `tests/` that reproduces
   the layout problem.
6. Only then consider the Claude analyzer, with an explicit `--yes`, and compare it with the
   heuristic report on the same papers.
