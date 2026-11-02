"""Heading recognition, section-kind classification and section assembly.

Classification is keyword-based on the heading text and therefore transparent;
subsections without a recognisable keyword inherit their parent's kind.
"""
from __future__ import annotations

import re

from .model import Block, Document, Section, SectionKind

# Ordered: first match wins.
KIND_KEYWORDS: list[tuple[SectionKind, str]] = [
    (SectionKind.ABSTRACT, r"^abstract\b"),
    (SectionKind.REFERENCES, r"^(references|bibliography|works cited|literature cited)\b"),
    (SectionKind.APPENDIX, r"\bappendix|appendices|online appendix|supplementary (material|appendix)|internet appendix"),
    (SectionKind.INTRODUCTION, r"\bintroduction\b"),
    (SectionKind.LITERATURE, r"\b(related (literature|work|research)|literature review|prior (literature|work)|relation to (the )?literature)\b"),
    (SectionKind.ROBUSTNESS, r"\b(robustness|sensitivity|additional (tests|analyses|results)|further (tests|evidence)|alternative specifications?)\b"),
    (SectionKind.CONCLUSION, r"\b(conclu(sion|sions|ding)|summary and|final remarks|discussion and conclu)"),
    (SectionKind.DATA, r"\b(data|sample|variables?|summary statistics|descriptive statistics)\b"),
    (SectionKind.METHODOLOGY, r"\b(method|methodology|empirical (strategy|framework|design|approach|specification)|estimation|identification|econometric|research design|approach|algorithm|architecture|training|implementation)\b"),
    (SectionKind.RESULTS, r"\b(results?|findings|empirical evidence|evidence|performance|main (tests|analysis)|out-of-sample|pricing performance|predictab)"),
    (SectionKind.THEORY, r"\b(model|theor(y|etical)|framework|hypothes[ie]s|setup|set-up|economic (motivation|framework|intuition)|asset pricing (model|framework)|stochastic discount factor|pricing kernel|mechanism)\b"),
]

_NUM = r"(?P<num>(?:\d{1,2}(?:\.\d{1,2}){0,3}|[A-H](?:\.\d{1,2}){0,2}|[IVX]{1,5}))"
NUMBERED_HEADING = re.compile(rf"^{_NUM}[.)]?\s+(?P<title>[A-Z][^\n]{{1,110}})$")
UNNUMBERED_HEADINGS = re.compile(
    r"^(abstract|introduction|conclusions?|concluding remarks|references|bibliography|appendix(\s+[A-Z])?(\s*[:.\-–]\s*.*)?|"
    r"online appendix|internet appendix|acknowledg(e)?ments|data|related literature|literature review)\s*$",
    re.IGNORECASE)


def classify_heading(title: str) -> SectionKind | None:
    t = title.lower().strip()
    for kind, rx in KIND_KEYWORDS:
        if re.search(rx, t):
            return kind
    return None


def parse_heading(text: str) -> tuple[str | None, str] | None:
    """Return (number, title) if ``text`` looks like a section heading line."""
    t = text.strip()
    if not t or len(t) > 120 or t.endswith((",", ";")):
        return None
    m = NUMBERED_HEADING.match(t)
    if m:
        title = m.group("title").strip()
        n_words = len(title.split())
        # Reject body sentences that merely start with a number or letter.
        long_sentence = n_words > 12 or (title.endswith(".") and n_words > 6)
        if not long_sentence and (re.search(r"[a-z]{2,}", title) or title.isupper()):
            return m.group("num"), title.rstrip(".")
    if UNNUMBERED_HEADINGS.match(t):
        return None, t.rstrip(".:")
    return None


def heading_level(number: str | None) -> int:
    if not number:
        return 1
    return number.count(".") + 1


def assemble_sections(doc: Document) -> None:
    """Assign ``section_id`` and ``paragraph`` to blocks; build ``doc.sections``.

    Blocks before the first heading go into a front-matter section. If a front
    block starts with "Abstract", it becomes the abstract section.
    """
    sections: list[Section] = []
    current: Section | None = None
    parent_kind: dict[int, str] = {}
    seen_references = False

    def new_section(title: str, number: str | None, kind: str, heading: Block | None) -> Section:
        s = Section(id=f"s{len(sections):02d}", title=title, number=number, level=heading_level(number),
                    kind=kind, heading_block=heading.id if heading else None)
        sections.append(s)
        return s

    for b in doc.blocks:
        if b.kind == "heading":
            parsed = parse_heading(b.text) or (None, b.text.strip())
            number, title = parsed
            level = heading_level(number)
            kind = classify_heading(title)
            if kind is None and level > 1 and current is not None:
                kind = SectionKind(parent_kind.get(level - 1, current.kind))
            if kind is None and seen_references and number and number[0].isalpha():
                kind = SectionKind.APPENDIX  # lettered sections after references
            if kind is None and current is not None and current.kind == SectionKind.APPENDIX.value:
                kind = SectionKind.APPENDIX
            kind = kind or SectionKind.OTHER
            if kind == SectionKind.REFERENCES:
                seen_references = True
            current = new_section(title, number, kind.value, b)
            parent_kind[level] = kind.value
        elif current is None:
            is_abs = re.match(r"^\s*abstract\b[\s.:—–-]*", b.text, re.IGNORECASE)
            current = new_section("Abstract" if is_abs else "Front matter", None,
                                  (SectionKind.ABSTRACT if is_abs else SectionKind.FRONT_MATTER).value, None)
        elif current.kind == SectionKind.FRONT_MATTER.value and re.match(r"^\s*abstract\b", b.text, re.IGNORECASE):
            current = new_section("Abstract", None, SectionKind.ABSTRACT.value, None)
        b.section_id = current.id
        current.block_ids.append(b.id)

    for s in sections:
        pages = [doc.block(i).page for i in s.block_ids if doc.block(i) and doc.block(i).page is not None]
        s.page_start, s.page_end = (min(pages), max(pages)) if pages else (None, None)
        n = 0
        for bid in s.block_ids:
            blk = doc.block(bid)
            if blk.kind != "heading":
                n += 1
                blk.paragraph = n
    doc.sections = sections
    if not any(s.heading_block for s in sections):
        doc.warnings.append("No section headings were detected; the paper is treated as one unsectioned body. "
                            "Section-specific analysis will be unreliable.")
    kinds = {s.kind for s in sections}
    for required in (SectionKind.INTRODUCTION, SectionKind.RESULTS, SectionKind.CONCLUSION):
        if required.value not in kinds and len(sections) > 1:
            doc.warnings.append(f"No '{required.value}' section was identified from the headings.")
