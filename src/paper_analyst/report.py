"""Deep research report: data model and Obsidian-compatible Markdown rendering.

Four item kinds are kept strictly apart:

* AUTHOR_CLAIM  - verbatim statement of the authors (question, contribution,
                  interpretation, conclusion). Exactly one source locator.
* EVIDENCE      - verbatim passage reporting data, sample construction, design
                  facts, estimates or statistics (incl. table text). Exactly one
                  source locator. "Directly supported" means the passage is in the
                  paper as quoted - not that the paper's numbers are correct.
* INTERPRETATION- analyst/AI reasoning. Must cite the blocks it relies on, or be
                  an explicit absence finding ("not found in the extracted text").
* SPECULATION   - research ideas beyond the paper. Clearly labelled; may not
                  introduce numbers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

REPORT_SECTIONS: dict[str, str] = {
    "research_question": "1. Research question and economic motivation",
    "contribution": "2. Contribution relative to existing literature",
    "theory": "3. Theoretical framework and economic mechanisms",
    "data": "4. Data, sample construction and variable definitions",
    "identification": "5. Empirical identification and estimation methodology",
    "findings": "6. Main findings (including quantitative results)",
    "robustness": "7. Robustness checks and limitations",
    "assessment": "8. Critical assessment of the research design",
    "implications": "9. Implications for future asset pricing research",
    "open_questions": "10. Open research questions and potential extensions",
}


class ItemKind(str, Enum):
    AUTHOR_CLAIM = "author_claim"
    EVIDENCE = "evidence"
    INTERPRETATION = "interpretation"
    SPECULATION = "speculation"


VERBATIM_KINDS = {ItemKind.AUTHOR_CLAIM.value, ItemKind.EVIDENCE.value}


@dataclass
class Locator:
    block_id: str
    page: int | None = None
    page_end: int | None = None
    printed_page: str | None = None
    section: str | None = None
    section_kind: str | None = None
    paragraph: int | None = None

    def render(self) -> str:
        parts = []
        if self.page is not None:
            parts.append(f"p. {self.page}" if self.page_end in (None, self.page) else f"pp. {self.page}–{self.page_end}")
            if self.printed_page and self.printed_page != str(self.page):
                parts[-1] += f" (printed {self.printed_page})"
        if self.section:
            parts.append(self.section)
        if self.paragraph:
            parts.append(f"¶{self.paragraph}")
        return ", ".join(parts) + f" [{self.block_id}]"


@dataclass
class ReportItem:
    kind: str
    text: str
    locators: list[Locator] = field(default_factory=list)
    basis: str = ""
    tags: list[str] = field(default_factory=list)   # e.g. "absence", "check:out_of_sample", "profile"


@dataclass
class DeepReport:
    paper_id: int | None
    title: str
    analyzer: str
    model: str | None
    profile: str
    source_type: str                     # pdf | text | abstract
    source_sha256: str | None
    source_path: str | None
    extractor: str
    sections: dict[str, list[ReportItem]] = field(default_factory=lambda: {k: [] for k in REPORT_SECTIONS})
    connections: list[dict] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    extraction_warnings: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    audit: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def items(self):
        for key, items in self.sections.items():
            for it in items:
                yield key, it

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DeepReport":
        d = dict(d)
        d["sections"] = {k: [ReportItem(kind=i["kind"], text=i["text"],
                                        locators=[Locator(**loc) for loc in i.get("locators", [])],
                                        basis=i.get("basis", ""), tags=i.get("tags", []))
                             for i in v] for k, v in d["sections"].items()}
        return cls(**d)

    def counts(self) -> dict[str, int]:
        c = {k.value: 0 for k in ItemKind}
        for _, it in self.items():
            c[it.kind] = c.get(it.kind, 0) + 1
        return c


# ---------------------------------------------------------------- rendering
_LABEL = {
    ItemKind.AUTHOR_CLAIM.value: "Author claims (verbatim)",
    ItemKind.EVIDENCE.value: "Directly supported evidence (verbatim)",
}


def _quote(text: str) -> str:
    return text.replace("\n", " | ")


def render_report(report: DeepReport, paper=None) -> str:
    from .export import frontmatter  # local import avoids a cycle
    out = []
    if paper is not None:
        fm = frontmatter(paper, None).rstrip("-\n").rstrip()
        out.append(fm + f"\nreport: deep\nanalyzer: {report.analyzer}\nmodel: {report.model or 'null'}\n"
                   f"source_type: {report.source_type}\nsource_sha256: {report.source_sha256 or 'null'}\n---")
    out += ["", f"# {report.title}", "", "## Provenance", "",
            f"- **Source:** {report.source_type}" + (f" `{report.source_path}`" if report.source_path else ""),
            f"- **SHA-256:** `{report.source_sha256}`" if report.source_sha256 else "- **SHA-256:** n/a",
            f"- **Extractor:** {report.extractor}",
            f"- **Analyzer:** {report.analyzer}" + (f" ({report.model})" if report.model else ""),
            f"- **Research profile:** {report.profile}",
            f"- **Generated:** {report.created_at}", ""]
    out += ["> [!info] How to read this report",
            "> - **Author claims** and **directly supported evidence** are verbatim quotes, each with a page/"
            "section/paragraph locator and block id, re-verified against the extracted text.",
            "> - **Evidence** means the passage is in the paper as quoted; it does not mean the paper's numbers "
            "have been independently replicated.",
            "> - **AI interpretations** are the analyzer's reasoning and cite the passages they rely on; "
            "*absence* findings mean \"not found in the extracted text\", not proof of omission.",
            "> - **Speculative research ideas** go beyond the paper and contain no quantitative claims.",
            "> - No citations are added beyond those that appear in the paper itself.", ""]
    a = report.audit
    if a:
        out += ["## Traceability audit", "",
                f"- Verbatim items verified against source: **{a.get('verbatim_verified', 0)}/{a.get('verbatim_total', 0)}**",
                f"- Interpretations with valid citations or explicit absence tag: "
                f"**{a.get('interpretations_ok', 0)}/{a.get('interpretations_total', 0)}**",
                f"- Unsupported numbers in interpretations/speculation: **{a.get('unsupported_numbers', 0)}**",
                f"- Items dropped during validation: **{a.get('dropped', 0)}**", ""]
    cov = report.coverage
    if cov:
        out += ["## Document coverage", "", "| Section type | Pages |", "|---|---|"]
        for kind, pages in cov.get("present", {}).items():
            out.append(f"| {kind} | {', '.join(map(str, pages)) or 'n/a'} |")
        if cov.get("missing"):
            out += ["", "Not detected: " + ", ".join(cov["missing"])]
        out.append("")
    if report.extraction_warnings:
        out += ["> [!warning] Extraction warnings"] + [f"> - {w}" for w in report.extraction_warnings] + [""]

    for key, title in REPORT_SECTIONS.items():
        items = report.sections.get(key, [])
        out += [f"## {title}", ""]
        for kind in (ItemKind.AUTHOR_CLAIM.value, ItemKind.EVIDENCE.value):
            rows = [i for i in items if i.kind == kind]
            if rows:
                out += [f"**{_LABEL[kind]}**", ""]
                out += [f'- "{_quote(i.text)}" — *{i.locators[0].render()}*' for i in rows]
                out.append("")
        interp = [i for i in items if i.kind == ItemKind.INTERPRETATION.value]
        if interp:
            out.append("> [!note] AI interpretation (not stated by the authors)")
            for i in interp:
                cites = "; ".join(loc.render() for loc in i.locators)
                extra = " ".join(x for x in [f"Basis: {i.basis.rstrip('.')}." if i.basis else "",
                                             f"See {cites}." if cites else ""] if x)
                out.append(f"> - {i.text}" + (f" _({extra})_" if extra else ""))
            out.append("")
        spec = [i for i in items if i.kind == ItemKind.SPECULATION.value]
        if spec:
            out.append("> [!question] Speculative research ideas (beyond the paper)")
            for i in spec:
                out.append(f"> - {i.text}" + (f" _(Basis: {i.basis})_" if i.basis else ""))
            out.append("")
        if not items:
            out += ["_Nothing found in the extracted text for this section._", ""]

    if report.connections:
        out += ["## Research-profile connections", "",
                "| Theme | Assessment | Rationale |", "|---|---|---|"]
        for c in report.connections:
            out.append(f"| {c['name']} | **{c['level']}** | {c['rationale'].replace('|', '/')} |")
        out.append("")
    if report.validation_warnings:
        out += ["## Validation log", ""] + [f"- {w}" for w in report.validation_warnings] + [""]
    return "\n".join(out)
