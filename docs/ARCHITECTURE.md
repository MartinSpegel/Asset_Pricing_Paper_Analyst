# Architecture

```
Discovery (MVP)
  SearchQuery -> Source.search() x3 -> apply_filters -> deduplicate -> rank -> Store.upsert
                 (OpenAlex/arXiv/S2, Transport = HttpTransport | MockTransport)

Full-paper analysis
  PDF / .txt / .md ── fulltext.load_document ──> Document (blocks + sections + page layouts + warnings)
                                                     │  stored in `documents`
                     ┌───────────────────────────────┴──────────────────────────┐
                     │ analysis.deep_heuristic.DeepHeuristicAnalyzer (offline)   │
                     │ analysis.deep_claude.ClaudeDeepAnalyzer (optional, paid)  │
                     │      both use init_report(): coverage + profile.assess_connections
                     └───────────────────────────────┬──────────────────────────┘
                                                     ▼
                                 verify.validate_report (mandatory for every analyzer)
                                                     ▼
                         DeepReport ── report.render_report ──> Markdown / Obsidian note
                                     └── stored in `reports`; verify.audit_report re-checks later
```

## Located document model (`fulltext/model.py`)

* **Block**: one paragraph, heading, caption, table, footnote or title. Each block stores:
  * a stable `id` (`b0042`) and its `kind`;
  * the physical `page` and `page_end`, and the `printed_page` label;
  * `column` (0 = full width, 1 = left, 2 = right), `bbox` and `section_id`;
  * `paragraph` (its index within the section);
  * `page_offsets`, so a quote inside a paragraph that crosses a page resolves to the correct
    page.
* **Section**: number, title, level, kind, page range and block ids. The kind is one of
  front_matter, abstract, introduction, literature, theory, data, methodology, results, robustness,
  conclusion, references, appendix or other.
* **Document**: the source path, source type, SHA-256, extractor version, blocks, sections,
  per-page layout, removed margin lines (logged, not silently lost), warnings and statistics.

## PDF extraction (`fulltext/pdf.py`)

The extractor is built on pdfplumber (pdfminer.six). Its stages:

1. **Word boxes → rows.** Rows are split into fragments at wide horizontal gaps, so the two
   columns and table cells separate.
2. **Margin cleanup.** Lines in the top and bottom margins that repeat across pages (running
   headers and footers) and bare page numbers are removed. Each removal is logged, and the page
   number is kept as `printed_page`.
3. **Gutter detection.** A two-column page is detected by an x-position that no fragment crosses,
   with text on both sides and an aligned left edge on the right. The table check rules out false
   positives. Pages are labelled `single`, `two_column` or `mixed` (full-width elements inside
   columns), and `mixed` pages raise a warning.
4. **Reading order.** Full-width regions are read in order; between them, the left column is read
   before the right.
5. **Line classification.** Each line becomes title, heading, caption, table, footnote or body:
   * headings: bold or large type with a heading pattern, or a regular-weight numbered or ALL-CAPS
     heading followed by a gap;
   * table rows: three or more cells, mostly numeric;
   * footnotes: small type in the lower part of the page.
6. **Paragraph merging.** Lines merge into paragraphs except at vertical spacing, first-line
   indents, short last lines and numbered or reference entries. Footnotes are kept out of the main
   flow, so they do not split paragraphs. Line-break hyphens are removed (and counted). Ligatures
   are normalised with NFKC.
7. **Sections.** `sections.assemble_sections` classifies headings by keyword. A subsection
   inherits its parent's kind, and lettered sections after the references become appendices.

**Failure policy.** These raise `ExtractionError` and nothing is extracted:

* not a PDF;
* encrypted without the right password;
* unparsable;
* no text layer on any page.

These become `warnings` on the document:

* pages without text (image-only pages are named, and OCR is not performed);
* garbled font encodings;
* mixed layouts;
* missing headings or expected sections;
* very little text.

No text is ever generated to fill a gap.

## Report and verification

* `report.py`: `DeepReport` has 10 fixed sections. A `ReportItem` has a `kind`: `author_claim`,
  `evidence`, `interpretation` or `speculation`. A `Locator` gives page(s), printed page, section,
  paragraph and block id.
* `verify.validate_report` enforces these rules on every analyzer's output:
  * verbatim kinds (author claims and evidence) must cite exactly one existing block and be found
    in it, tolerant only to whitespace, case, curly quotes and dashes;
  * locators are **recomputed from the document**;
  * interpretations need at least one valid citation, or an explicit `absence` tag;
  * interpretations and speculation may not contain numbers or author-year citations absent from
    the blocks they cite.

  Failures are dropped and logged in the report's validation log.
* `verify.audit_report` runs the same checks read-only. It also detects tampered locators and a
  changed source hash. `paper-analyst audit` uses it.

## Heuristic deep analyzer (`analysis/deep_heuristic.py`)

* Sentences keep their block. Each sentence is assigned to at most one report section, scored by
  the type of document section it comes from plus cue phrases; at least one cue is required.
* Sentences that report figures, dates or counts are labelled evidence; other selected sentences
  are author claims.
* Tables and captions from results, robustness, data and appendix sections are added as evidence.
* A design checklist covers:
  * out-of-sample evaluation and validation-sample tuning;
  * look-ahead bias;
  * inference;
  * multiple testing;
  * transaction costs;
  * benchmarks;
  * economic significance;
  * sample filters;
  * cross-country heterogeneity;
  * mechanism identification ("consistent with" versus exogenous variation).

  Each check produces an interpretation in one of three forms: addressed (with citations),
  acknowledged as not addressed (the passage contains negation), or not found in the extracted
  text (an absence finding).
* Profile connections become implications, and extension templates become speculation.

## Storage

The MVP tables are `papers` and `analyses`. Two tables are added, both created with
`CREATE TABLE IF NOT EXISTS`, so existing databases upgrade in place:

* `documents`: the full located document as JSON, plus its hash, extractor and warnings;
* `reports`: report JSON and Markdown, analyzer, model, profile and source hash.

Both keep their history: a new row is added on every ingest or analysis.
