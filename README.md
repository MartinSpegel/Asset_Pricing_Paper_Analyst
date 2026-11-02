# Asset Pricing Paper Analyst

A command-line research assistant for **empirical asset pricing and machine learning in finance**.
It finds working papers through free scholarly APIs, deduplicates them, stores them in SQLite,
ranks them against a research agenda and writes structured research memos. The memos export to
Obsidian.

* **Discovery:** [OpenAlex](https://docs.openalex.org), [arXiv](https://info.arxiv.org/help/api/)
  and [Semantic Scholar](https://api.semanticscholar.org/api-docs/graph). All three are free and
  need no API key.
* **Filters:** researcher, keywords, publication date range and research-topic presets.
* **Deduplication:** by DOI, arXiv id (version-less) and normalised title. Records are merged across
  sources, keeping the richest metadata from each.
* **Storage:** SQLite holds metadata, abstract, URLs, sources, research status, notes, relevance
  scores and analysis history.
* **Ranking:** transparent, auditable keyword scoring for international asset pricing, stochastic
  discount factors, return predictability, transfer learning and ML in finance.
* **Memos:** sections for research question, economic mechanism, methodology, data, results,
  limitations and research implications.
* **Evidence vs. interpretation:** every source-supported claim is a verbatim quote with a
  locator, and the code checks it against the source text. Interpretations are labelled
  separately. Results and citations are never invented.
* **Obsidian export:** YAML front matter, tags, callouts and a Map-of-Content index note
  with `[[wikilinks]]`.
* **Offline demo:** mocked API responses, so everything can be tested with no network and no
  paid API.
* **Optional Claude analyzer:** off by default and never called unless you ask for it
  (see [Cost](#optional-claude-integration-and-cost)).

> The bundled demo papers are **synthetic**. Fake DOIs use the `10.5555` test prefix and fake
> arXiv ids look like `9901.xxxxx`. Do not cite them.

## Setup

Requires Python ≥ 3.10.

```bash
git clone <this repo> && cd Asset_Pricing_Paper_Analyst
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # core + pytest
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

## Quick start: offline demo

```bash
paper-analyst demo --out demo_output
```

The demo runs the whole pipeline on mocked OpenAlex, arXiv and Semantic Scholar responses:

* 12 raw results are fetched.
* After filtering, 9 remain. Deduplication merges those into 5 unique papers.
* The papers are ranked, the top 5 are analyzed, and the results are exported to
  `demo_output/vault/` (open that folder as an Obsidian vault).

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
```

Global option: `--db PATH`. Run `paper-analyst <command> --help` for every flag.

**Topic presets** (`-t`): `international_asset_pricing`, `sdf`, `return_predictability`,
`transfer_learning`, `machine_learning`. Any other text is treated as a free-text keyword.

**Research statuses:** `new` → `screening` → `to_read` → `reading` → `analyzed`, plus `archived`
and `rejected`. Running `analyze` moves `new`, `screening` and `to_read` papers to `analyzed`.

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

Setup:

```bash
pip install -e ".[claude]"
export ANTHROPIC_API_KEY=...        # never commit it
paper-analyst analyze --id 1 --analyzer claude --yes
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

The 47 tests cover:

* parsing each API's response format;
* query construction;
* filters, deduplication (including bridging records), ranking and SQLite persistence;
* memo validation (invented claims are dropped);
* the heuristic and Claude analyzers (Claude through a fake client);
* Obsidian export, end-to-end CLI flows, and a scan that keeps API keys out of the repo.

CI runs the tests and the demo on Python 3.10, 3.12 and 3.13 (`.github/workflows/tests.yml`).

## Project layout

```
src/paper_analyst/
  cli.py            command-line interface
  pipeline.py       discover -> filter -> dedup -> rank -> store
  sources/          openalex.py, arxiv.py, semantic_scholar.py
  http.py           live HTTP transport (retry/backoff) + offline MockTransport
  filters.py        SearchQuery, topic presets, local filtering
  normalize.py      DOI / arXiv / title normalisation
  dedup.py          cross-source merge
  ranking.py        agenda relevance scoring
  storage.py        SQLite store (papers, analyses)
  memo.py           memo data model + verbatim-quote validation
  analysis/         heuristic.py (offline), claude.py (optional)
  export.py         Markdown rendering + Obsidian vault export
  mock_data/        synthetic API responses for offline use
sample_data/        sample full text + notes on the mock corpus
scripts/            build_mock_data.py
docs/ARCHITECTURE.md
tests/
```

## Limitations and next steps

* Memos use abstracts unless you supply full text. PDF download and text extraction are not
  implemented yet; `pypdf` would be a natural addition.
* The heuristic analyzer is extractive and cue-based. It can misfile a sentence, but it cannot
  invent one.
* Live-API parsing follows each API's documented response format. It has been tested against
  the mocks only; this build environment had no outbound access to the APIs.
* Ideas for later: scheduled alerts for new papers by followed researchers, citation-graph
  expansion (OpenAlex `referenced_works`), embedding-based ranking, and BibTeX export.
