"""Traceability verification for deep reports.

``validate_report`` is applied to the output of *every* analyzer (heuristic or
LLM): items that fail are removed and logged, and locators are recomputed from
the document so that page numbers never come from the analyzer itself.
``audit_report`` performs the same checks read-only (e.g. on a stored report).
"""
from __future__ import annotations

import copy
import re

from .fulltext.model import Document
from .report import DeepReport, ItemKind, Locator, ReportItem, VERBATIM_KINDS

_TRANS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-",
                        "—": "-", "−": "-", " ": " "})
MIN_QUOTE_CHARS = 20
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)*(?:\.\d+)?%?")
_AUTHOR_YEAR = re.compile(r"\b[A-Z][a-zA-Z\-]+(?: et al\.?| and [A-Z][a-zA-Z\-]+)?,?\s*\(?(?:19|20)\d{2}[a-z]?\)?")


def canonical(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_TRANS)).strip().lower()


def find_span(block_text: str, quote: str) -> tuple[int, int] | None:
    """Locate ``quote`` in ``block_text`` tolerant to whitespace, case, curly quotes and dashes.

    Returns character offsets into the original block text.
    """
    tokens = canonical(quote).rstrip(".").split()
    if not tokens:
        return None
    hay = block_text.translate(_TRANS).lower()  # length-preserving
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    m = re.search(pattern, hay)
    return (m.start(), m.end()) if m else None


def numbers_in(text: str) -> set[str]:
    out = set()
    for n in _NUMBER.findall(text):
        n = n.replace(",", "").rstrip("%").lstrip("+")
        if n.startswith("-"):
            n = n[1:]
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def make_locator(doc: Document, block_id: str, quote: str | None = None) -> Locator | None:
    b = doc.block(block_id)
    if b is None:
        return None
    s = doc.section_of(b)
    page, page_end = b.page, b.page_end
    if quote:
        span = find_span(b.text, quote)
        if span is None:
            return None
        page, page_end = b.pages_for_span(*span)
    return Locator(block_id=b.id, page=page, page_end=page_end, printed_page=b.printed_page,
                   section=s.label if s else None, section_kind=s.kind if s else None, paragraph=b.paragraph)


def _check_item(item: ReportItem, doc: Document) -> tuple[ReportItem | None, list[str], dict]:
    """Return (fixed item or None if rejected, problems, flags)."""
    problems: list[str] = []
    flags = {"unsupported_number": False}
    if item.kind in VERBATIM_KINDS:
        if len(item.locators) != 1:
            return None, [f"verbatim item must cite exactly one block (got {len(item.locators)})"], flags
        if len(canonical(item.text)) < MIN_QUOTE_CHARS:
            return None, ["quote too short to be meaningful"], flags
        loc = make_locator(doc, item.locators[0].block_id, item.text)
        if loc is None:
            return None, [f"quote not found verbatim in cited block {item.locators[0].block_id}"], flags
        fixed = copy.copy(item)
        fixed.locators = [loc]
        return fixed, problems, flags

    valid = [make_locator(doc, loc.block_id) for loc in item.locators]
    valid = [v for v in valid if v is not None]
    if len(valid) < len(item.locators):
        problems.append("dropped citation(s) to unknown blocks")
    if item.kind == ItemKind.INTERPRETATION.value and not valid and "absence" not in item.tags:
        return None, problems + ["interpretation cites no source passage and is not an absence finding"], flags
    cited_text = " ".join(doc.block(v.block_id).text for v in valid)
    unsupported = numbers_in(item.text) - numbers_in(cited_text)
    if unsupported:
        flags["unsupported_number"] = True
        return None, problems + [f"contains number(s) not present in cited passages: {sorted(unsupported)}"], flags
    for m in _AUTHOR_YEAR.finditer(item.text):
        if canonical(m.group(0)) not in canonical(cited_text):
            return None, problems + [f"contains a citation not present in cited passages: {m.group(0)!r}"], flags
    fixed = copy.copy(item)
    fixed.locators = valid
    return fixed, problems, flags


def validate_report(report: DeepReport, doc: Document) -> DeepReport:
    stats = {"verbatim_total": 0, "verbatim_verified": 0, "interpretations_total": 0, "interpretations_ok": 0,
             "unsupported_numbers": 0, "dropped": 0}
    for key, items in report.sections.items():
        kept = []
        for it in items:
            fixed, problems, flags = _check_item(it, doc)
            is_verbatim = it.kind in VERBATIM_KINDS
            stats["verbatim_total" if is_verbatim else "interpretations_total"] += 1
            stats["unsupported_numbers"] += flags["unsupported_number"]
            if fixed is None:
                stats["dropped"] += 1
                report.validation_warnings.append(f"[{key}] dropped {it.kind}: {'; '.join(problems)} — {it.text[:100]!r}")
                continue
            for p in problems:
                report.validation_warnings.append(f"[{key}] {it.kind}: {p}")
            stats["verbatim_verified" if is_verbatim else "interpretations_ok"] += 1
            kept.append(fixed)
        report.sections[key] = kept
    # After dropping, everything that remains is verified.
    report.audit = {**stats, "verbatim_total": stats["verbatim_verified"],
                    "interpretations_total": stats["interpretations_ok"], "unsupported_numbers": 0,
                    "dropped": stats["dropped"], "unsupported_numbers_dropped": stats["unsupported_numbers"]}
    return report


def audit_report(report: DeepReport, doc: Document) -> dict:
    """Read-only re-verification (e.g. of a stored report against a re-extracted document)."""
    issues = []
    stats = {"verbatim_total": 0, "verbatim_verified": 0, "interpretations_total": 0, "interpretations_ok": 0,
             "unsupported_numbers": 0, "locator_mismatches": 0}
    if report.source_sha256 and doc.sha256 and report.source_sha256 != doc.sha256:
        issues.append("source document hash differs from the one the report was generated from")
    for key, it in report.items():
        fixed, problems, flags = _check_item(it, doc)
        is_verbatim = it.kind in VERBATIM_KINDS
        stats["verbatim_total" if is_verbatim else "interpretations_total"] += 1
        stats["unsupported_numbers"] += flags["unsupported_number"]
        if fixed is None:
            issues.append(f"[{key}] {it.kind}: {'; '.join(problems)} — {it.text[:80]!r}")
            continue
        stats["verbatim_verified" if is_verbatim else "interpretations_ok"] += 1
        if is_verbatim:
            old, new = it.locators[0], fixed.locators[0]
            if (old.page, old.page_end, old.section) != (new.page, new.page_end, new.section):
                stats["locator_mismatches"] += 1
                issues.append(f"[{key}] locator mismatch: stored {old.render()} vs source {new.render()}")
    stats["issues"] = issues
    stats["ok"] = not issues
    return stats
