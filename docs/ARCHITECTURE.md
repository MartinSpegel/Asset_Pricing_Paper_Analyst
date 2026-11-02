# Architecture

```
 SearchQuery ──► Source.search() ×3 ──► apply_filters ──► deduplicate ──► rank ──► Store.upsert
                 (OpenAlex/arXiv/S2)     (local, uniform)  (DOI/arXiv/title)        (dedup-aware)
                         │
                   Transport (HttpTransport | MockTransport)

 Store ──► Analyzer.analyze(paper, full_text?) ──► validate_memo ──► render_memo ──► export_obsidian
           (HeuristicAnalyzer | ClaudeAnalyzer)    (verbatim check)  (Markdown)      (vault + index)
```

## Design decisions

* **Transport injection.** Each source receives a `Transport`. `MockTransport` returns bundled
  fixtures and records the requests it receives, so the tests can check both parsing and the
  exact API parameters without network access.
* **Filters run twice.** Each source pushes what its API supports: dates on all three, author ids
  on OpenAlex, and `au:` and categories on arXiv. `filters.matches` then re-applies every
  criterion locally, so results from different sources are consistent.
* **Deduplication** links records that share any key (`doi:`, `arxiv:` or `title:`). A record
  that shares a DOI with one group and an arXiv id with another merges the two groups. Titles
  shorter than 15 normalised characters are not used as keys, which avoids false merges on titles
  like "Comment". The SQLite store repeats the same lookup on insert, so repeated discoveries
  merge into existing rows. Partial unique indexes on `doi` and `arxiv_id` enforce this.
* **Evidence and interpretation are different types.** `SourceClaim` and `Interpretation` are
  separate dataclasses, so no code path can turn one into the other. `validate_memo` checks every
  analyzer's output, so the guarantee does not depend on prompt compliance.
* **Ranking is a transparent heuristic**, not a learned model, so the score can be explained in
  the memo and tuned by editing `DEFAULT_TOPICS`.

## Database schema

`papers` columns:

* `id`, `title`, `norm_title`, `authors` (JSON), `abstract`, `publication_date`, `venue`
* identifiers: `doi`, `arxiv_id`, `openalex_id`, `s2_id`
* `urls` (JSON), `sources` (JSON), `topics` (JSON)
* triage: `status`, `relevance_score`, `relevance_breakdown` (JSON), `notes`
* `created_at`, `updated_at`

`analyses` columns:

* `id`, `paper_id`, `analyzer`, `model`
* `memo_json`, `memo_markdown`
* `created_at`

Each run adds a new `analyses` row, so the history of every memo is kept.
