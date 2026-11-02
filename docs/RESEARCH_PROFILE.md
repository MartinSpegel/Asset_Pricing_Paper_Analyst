# Research profile

The research profile (`src/paper_analyst/profiles/default.toml`, or your own file passed with
`--profile`) describes your agenda. Deep analysis uses it to say how a paper connects to your work,
and to tell **genuine research connections** apart from **superficial keyword overlap**.

## Themes

Each theme has:

* `concept_terms`: vocabulary that only *mentions* the topic. These are counted everywhere,
  including the introduction, literature review and reference list.
* `substantive_patterns`: case-insensitive regexes that indicate the paper *does* something on the
  topic, such as estimating an SDF, using a country panel, training and validating a model, or
  stating an identification strategy. They count **only in core sections**: theory, data,
  methodology, results, robustness and appendix. Reference entries never count.
* `questions`: your open questions. When a paper connects genuinely, these appear as clearly
  labelled speculative prompts.

The default profile covers five themes:

* international asset pricing and global equity markets;
* SDFs and pricing kernels;
* machine learning and transfer learning;
* cross-country return predictability;
* economic interpretation and empirical identification.

## Levels

| Level | Rule (defaults in `[assessment]`) |
|---|---|
| **genuine** | Substantive matches in at least 2 distinct core section kinds, or at least 3 in methodology and results combined |
| **partial** | At least 1 substantive match in a core section |
| **superficial** | Concept terms or substantive patterns only outside core sections, such as the introduction, literature review, conclusion or references. The report tells you not to treat the paper as evidence on this theme |
| **absent** | No mentions |
| **unverified** | No section structure, e.g. abstract only, so the distinction cannot be made |

Every match is stored with its block id, so a level can be traced back to the exact paragraphs that
caused it.

## Extensions

`[[extensions]]` entries generate **speculative** research ideas. An idea fires when every theme in
`requires` is genuine or partial, and every theme in `lacks` is superficial or absent. For example,
a paper that genuinely estimates an SDF but never leaves one market triggers "test whether the SDF
prices assets outside the estimation market". Ideas must not contain numbers; the validator drops
them otherwise.

## Writing your own

```bash
cp src/paper_analyst/profiles/default.toml my_profile.toml
paper-analyst profile --profile my_profile.toml          # validates regexes and theme references
paper-analyst deep-analyze --id 3 --profile my_profile.toml
```

Tips:
* Make substantive patterns specific to *actions*, such as "estimate … SDF", "predictive
  regression" or "N countries", rather than topic words.
* Test new patterns on a paper that only cites the topic: it should come out superficial.
