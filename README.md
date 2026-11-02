# Asset Pricing Paper Analyst

A command-line research analyst for **empirical asset pricing and machine learning in finance**.
It finds working papers, ingests the full PDF and writes a **traceable 10-section research
report**. Every author claim and every piece of evidence in the report is a verbatim quote with a
page, section and paragraph locator, and the code checks each one against the source.

**Discovery and triage**
* Searches the free [OpenAlex](https://docs.openalex.org), [arXiv](https://info.arxiv.org/help/api/)
  and [Semantic Scholar](https://api.semanticscholar.org/api-docs/graph) APIs.
* Filters by researcher, keywords, dates and topic.
* Deduplicates by DOI, arXiv id and title.
* Stores papers in SQLite with research status and notes, and ranks them by relevance.

**Full-paper ingestion** (`ingest`, `extract`)
* Reads local PDFs, `.txt` and `.md` files.
* Records the physical page, printed page label and column for each paragraph, and keeps a
  paragraph's page offsets when it crosses a page.
* Reconstructs two-column reading order.
* Removes running headers, footers and page numbers, and logs what it removed.
* Recognises footnotes, tables and captions.
* Identifies the abstract, introduction, literature review, theory, data, methodology, results,
  robustness, conclusion, references and appendix.
* Handles failures explicitly:
  * encrypted, scanned/image-only and corrupt PDFs raise clear errors;
  * pages without a text layer, garbled fonts and ambiguous layouts produce warnings;
  * no text is ever generated to fill a gap.

**Deep analysis** (`deep-analyze`) produces a report with ten sections:
1. research question and economic motivation;
2. contribution relative to the literature;
3. theory and economic mechanisms;
4. data, sample construction and variables;
5. identification and estimation;
6. main findings, including quantitative results;
7. robustness and limitations;
8. critical assessment of the research design;
9. implications for asset pricing research;
10. open questions and extensions.

Report content falls into four strictly separated kinds:

| Kind | What it is | Rule enforced in code |
|---|---|---|
| **Author claim** | The authors' statement of a question, contribution, interpretation or conclusion | Verbatim; exactly one cited block; page and section recomputed from the document |
| **Directly supported evidence** | A reported number, sample fact, variable definition, design fact or table text | Verbatim; exactly one cited block. "Supported" means the passage is in the paper, not that its numbers were replicated |
| **AI interpretation** | The analyzer's own reasoning | Must cite the passages it relies on, or be an explicit "not found in the extracted text" finding. Numbers and author-year citations that are not in the cited passages are rejected |
| **Speculative research idea** | An idea that goes beyond the paper | Clearly labelled; may not introduce numbers |

**Research profile** (`profile`, `--profile`). A configurable TOML file describes your agenda: international
asset pricing, SDFs and pricing kernels, machine and transfer learning, cross-country
predictability, and economic interpretation and identification. A theme counts as a **genuine**
connection only when the paper does substantive work on it in its core sections. Mentions confined
to the introduction, literature review or references are reported as **superficial keyword
overlap**. See [docs/RESEARCH_PROFILE.md](docs/RESEARCH_PROFILE.md).

**Verification** (`audit`). This command re-checks every quote, locator and number in a stored
report against the source document. It fails if anything was altered or the source file changed.

**Offline by default.**
* The heuristic analyzers need no network and no paid API.
* The optional Claude analyzers are never called without an explicit `--yes`
  (see [Cost](#optional-claude-integration-and-cost)).

> **What has and has not been validated:** see [docs/VALIDATION.md](docs/VALIDATION.md). All
> automated tests use **synthetic** documents with known ground truth, because real papers could not
> be downloaded in the development environment. They test extraction and traceability mechanics.
> They are **not** evidence of scientific accuracy on real papers. Validate on papers you know
> before relying on the reports.

## Setup

Requires Python ≥ 3.10.

```bash
git clone <this repo> && cd Asset_Pricing_Paper_Analyst
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # core (incl. pdfplumber) + pytest + reportlab (test fixtures)
# optional: pip install -e ".[claude]"   # only if you want the Claude analyzer
```

Optional environment variables go in your shell or in a git-ignored `.env`.
See `.env.example`; **never commit API keys**.

| Variable | Purpose |
|---|---|
| `OPENALEX_MAILTO` | Your email, which joins OpenAlex's faster "polite pool" (free) |
| `SEMANTIC_SCHOLAR_API_KEY` | Free key that raises Semantic Scholar rate limits (optional) |
| `PAPER_ANALYST_DB` | SQLite path (default `papers.db`) |
| `PAPER_ANALYST_OFFLINE` | `1` makes every command use the mocked responses |
| `ANTHROPIC_API_KEY` | Only needed for `--analyzer claude` (billed separately, see below) |
| `PAPER_ANALYST_CLAUDE_MODEL` | Claude model id (default `claude-opus-5-5`) |

## Quick start: offline demos

```bash
paper-analyst demo --out demo_output            # discovery -> dedup -> rank -> memos -> Obsidian
paper-analyst demo-fulltext --out demo_output   # PDF -> located document -> 10-section report -> audit
```

`demo-fulltext` ingests `sample_data/demo_paper.pdf`, a **synthetic** two-column paper built for
testing (see [sample_data/README.md](sample_data/README.md)). It writes a report to
`demo_output/vault/Reports/` and checks it with the audit.

To try your own paper:

```bash
paper-analyst demo-fulltext --pdf path/to/paper.pdf --out demo_output
```

## Usage

```bash
# Discover (live APIs; add --offline to use mocks)
paper-analyst discover -t sdf -t transfer_learning --from 2020
paper-analyst discover -k "stochastic discount factor" -k "machine learning" --all --from 2019-01 --to 2024
paper-analyst discover -a "Ada Lindqvist" -t return_predictability --source openalex --source arxiv

# Inspect and triage
paper-analyst list --min-score 40
paper-analyst list --status to_read --order date
paper-analyst show 3            # rendered memo (or abstract if not yet analyzed)
paper-analyst show 3 --json
paper-analyst status            # counts per status
paper-analyst status 3 to_read --notes "Compare with my SDF transfer setup"
paper-analyst rank              # recompute scores after editing ranking.py

# Analyze (offline heuristic by default)
paper-analyst analyze --top 10
paper-analyst analyze --id 3 --text-file paper3.txt    # use full text you supply

# Export to Obsidian
paper-analyst export --vault ~/Obsidian/Research --folder Papers --min-score 30

# Full paper: extract (inspect only), ingest, analyze, audit
paper-analyst extract paper.pdf --markdown paper.extracted.md   # check extraction against the PDF
paper-analyst ingest paper.pdf                  # creates/matches a paper; or --id 3 to attach
paper-analyst ingest locked.pdf --password ...  # encrypted PDFs
paper-analyst deep-analyze --id 3 --out ~/Obsidian/Research
paper-analyst deep-analyze --id 3 --profile my_profile.toml
paper-analyst show 3 --report
paper-analyst audit --id 3                      # re-verify stored report vs stored text
paper-analyst audit --id 3 --source paper.pdf   # ... or vs a fresh extraction of the file
paper-analyst profile                           # show/validate the research profile
```

Global option: `--db PATH`. Run `paper-analyst <command> --help` for every flag.

**Topic presets** (`-t`): `international_asset_pricing`, `sdf`, `return_predictability`,
`transfer_learning`, `machine_learning`. Any other text is treated as a free-text keyword.

**Research statuses:** `new` → `screening` → `to_read` → `reading` → `analyzed`, plus `archived`
and `rejected`. Running `analyze` moves `new`, `screening` and `to_read` papers to `analyzed`.

## Full-paper workflow and report anatomy

1. **`ingest`** extracts the file. The located document is stored in SQLite, keyed by its SHA-256.
   The command prints the detected sections with their page ranges and any extraction warnings.
   If no paper id is given, it creates a paper from the extracted title and abstract. Nothing is
   inferred that the document does not contain; authors and year stay empty unless known.
2. **`deep-analyze`** writes the report. If no full text has been ingested, it falls back to the
   abstract with a prominent **ABSTRACT ONLY** warning, and profile connections become
   `unverified`.
3. The report begins with a **provenance** block: file path, SHA-256, extractor version, analyzer,
   model and profile. Then come the **traceability audit**, the **document coverage** (which
   section types were found, on which pages) and the extraction warnings, followed by the ten
   sections.
4. Inside each section, author claims and evidence are bullet quotes followed by
   `p. 2, §6 Empirical Results, ¶1 [b0022]`. Interpretations appear in a `[!note]` callout with
   their basis and citations, and speculation in a `[!question]` callout.
5. Section 8, the **critical assessment**, is a transparent checklist:
   * out-of-sample design and validation-sample tuning;
   * look-ahead bias;
   * inference;
   * multiple testing;
   * transaction costs;
   * benchmarks;
   * economic significance;
   * sample filters;
   * cross-country heterogeneity;
   * whether the mechanism is identified or merely "consistent with" the evidence.

   Each item reads *addressed* (with citations), *acknowledged as not addressed by the authors*,
   or *not found in the extracted text*. The last means "verify in the paper", not proof that the
   paper omits it.
6. Sections 9 and 10 use the research profile: genuine and superficial connections are cited, and
   profile templates produce labelled speculative extensions.

The offline heuristic analyzer only **selects and labels** passages. It cannot judge whether an
argument is correct. Its value is a fast, fully traceable map of where the paper states what.
The optional Claude deep analyzer adds real reasoning, under the same validation rules.

## How memos avoid invented content

1. **Source text:** a memo is built only from the abstract or from a full text you supply with
   `--text-file`. Metadata is context, not evidence.
2. **Source-supported claims** must be verbatim quotes. `memo.validate_memo` checks every quote
   against the source text; whitespace, curly quotes and dashes are normalised before the check.
   It drops anything not found and records it under *Validation warnings*. Each claim that passes
   gets a locator such as `abstract, sentence 4` or `full text, paragraph 10`.
3. **Interpretations** are stored apart from claims, each with a stated *basis*. In Markdown they
   appear in a `> [!note] Interpretation (not stated in source)` callout.
4. **Empty sections:** if a section has no supporting text, the memo says
   *"Not stated in the available source text."* instead of filling the gap.
5. **No external citations:** the memo schema has no field for references. The Claude prompt
   forbids citing other work, and any quote that is not in the source text is removed.

The default **heuristic analyzer** is deterministic and offline. It assigns each sentence to its
best-matching section by weighted cue phrases. Its only interpretations are rule-based notes, such
as detected method families and agenda relevance. It cannot reason about a paper; the optional
Claude analyzer can.

## Relevance ranking

`ranking.py` defines five weighted topics, each with weighted terms. For each topic, title matches
count double and repeated body matches are capped. A saturating transform gives a 0–100 topic
score, and the topic scores are combined into an overall 0–100 score. A paper active in three or
more topics gets a 15% bonus, because the target niche is the intersection of these topics.

Each score is stored with its breakdown of matched terms, so a ranking can be explained. To tune
it to your agenda, edit `DEFAULT_TOPICS` and run `paper-analyst rank`.

## Optional Claude integration and cost

`paper-analyst analyze --analyzer claude --yes` sends the abstract, or the `--text-file` text, to
the Claude API. It asks for a JSON memo (structured outputs), then runs the same verbatim-quote
validation as the heuristic analyzer.

> **Billing:** Claude API calls are billed per token by Anthropic to the account that owns
> `ANTHROPIC_API_KEY`. That billing is **separate from Claude Code cloud-session credits and from
> any Claude.ai subscription**, and building or testing this project does not use your API account.
> The CLI asks for an explicit `--yes` before any paid call. The tests use a fake client, so they
> never call the API.

There are two Claude entry points:

* `analyze --analyzer claude --yes`: short memo from the abstract (MVP).
* `deep-analyze --analyzer claude --yes`: full-paper report.
  * The paper is sent as numbered blocks, and the model must cite block ids.
  * Output streams and is constrained to a JSON schema.
  * Before asking for `--yes`, the CLI prints an **input-token estimate**. A full paper is
    typically tens of thousands of input tokens per run.
  * Page numbers in the report are always recomputed from the document, never taken from the
    model.
  * Any non-verbatim quote, uncited interpretation, or number or citation that is not in the cited
    text is dropped and logged.

Setup:

```bash
pip install -e ".[claude]"
export ANTHROPIC_API_KEY=...        # never commit it
paper-analyst analyze --id 1 --analyzer claude --yes
paper-analyst deep-analyze --id 1 --analyzer claude --yes
```

Choose a model with `--model` or `PAPER_ANALYST_CLAUDE_MODEL`. The default is `claude-opus-5-5`;
smaller models such as `claude-haiku-5-5` cost less per token.

Requests enable the API's server-side refusal fallback (`fallbacks: "default"`). If a safety
classifier declines a request, it is retried on a recommended fallback model. To turn this off,
construct `ClaudeAnalyzer(use_fallbacks=False)`.

## Tests

```bash
pytest -q
```

There are 95 tests, all offline. They cover discovery and parsing, filters, deduplication, ranking
and storage. They also cover:

* PDF extraction against ground truth: page, section and reading order for every paragraph of the
  synthetic demo PDF;
* layout and failure fixtures: two-column, hyphenation, headers, encrypted, image-only and corrupt
  PDFs;
* section classification;
* adversarial verification: fabricated quotes, numbers and citations are dropped, and tampering is
  detected;
* genuine-versus-superficial profile assessment;
* both deep analyzers (Claude only through a fake streaming client);
* all CLI workflows, and a scan that keeps API keys out of the repository.

See [docs/VALIDATION.md](docs/VALIDATION.md) for what is tested, what is not, and a protocol for
validating on your own papers. CI runs on Python 3.10, 3.12 and 3.13.

## Project layout

```
src/paper_analyst/
  cli.py              command-line interface
  pipeline.py         discover -> filter -> dedup -> rank -> store
  sources/            openalex.py, arxiv.py, semantic_scholar.py
  http.py, filters.py, normalize.py, dedup.py, ranking.py, storage.py
  fulltext/           model.py (Document/Block/Section), pdf.py (layout-aware extraction),
                      sections.py (heading + section-kind detection), text.py (plain text, abstract)
  profile.py          research profile + genuine/superficial connection assessment
  profiles/default.toml
  report.py           DeepReport (10 sections, 4 item kinds) + Markdown rendering
  verify.py           validate_report / audit_report (traceability enforcement)
  analysis/           heuristic.py, claude.py (abstract memos);
                      deep_heuristic.py (offline), deep_claude.py (optional) - full-paper reports
  memo.py, export.py  MVP memo model, Obsidian export (papers, index, reports)
  mock_data/          synthetic API responses
sample_data/          synthetic demo PDF + ground truth, sample text
scripts/              build_mock_data.py, build_demo_pdf.py (+ demo_paper_content.py)
docs/                 ARCHITECTURE.md, VALIDATION.md, RESEARCH_PROFILE.md
tests/
```

## Limitations and next steps

* There is **no OCR**: scanned PDFs are rejected with a clear message. Run `ocrmypdf` first.
* Equations, complex tables and figures are extracted poorly. Quotes that include them may fail
  verification; they are dropped, never repaired.
* Layouts with more than two columns and rotated pages are not supported.
* Section classification, sentence selection, the design checklist and the profile patterns are
  keyword and regex based and fully transparent. They need calibration on real papers; see
  [docs/VALIDATION.md](docs/VALIDATION.md).
* Ideas for later:
  * use the profile to drive relevance ranking;
  * table-structure extraction;
  * reference parsing linked to OpenAlex (only for references that actually appear in the paper);
  * evaluation scripts that compare reports against expert annotations.
