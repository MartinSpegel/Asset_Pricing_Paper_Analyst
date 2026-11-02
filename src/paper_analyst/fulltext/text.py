"""Plain-text / Markdown ingestion (no page information) and abstract-only documents."""
from __future__ import annotations

import hashlib
import re

from .model import Block, Document
from .sections import assemble_sections, parse_heading


def document_from_text(text: str, source_path: str | None = None, title: str | None = None) -> Document:
    doc = Document(source_path=source_path, source_type="text", title=title,
                   sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), extractor="plain-text v1")
    doc.warnings.append("Plain-text source: no page numbers are available; locators use sections and paragraphs.")
    i = 0
    for para in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in para.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        # A heading may be the first line of a paragraph block.
        first = re.sub(r"^#+\s*", "", lines[0])
        if (lines[0].startswith("#") or parse_heading(first)) and len(first) < 110:
            doc.blocks.append(Block(id=f"b{i:04d}", text=first, kind="heading"))
            i += 1
            lines = lines[1:]
        if lines:
            doc.blocks.append(Block(id=f"b{i:04d}", text=" ".join(lines), kind="paragraph"))
            i += 1
    if doc.title is None and doc.blocks and doc.blocks[0].kind == "paragraph" and len(doc.blocks[0].text) < 200:
        doc.title = doc.blocks[0].text
    assemble_sections(doc)
    doc.stats = {"blocks": len(doc.blocks), "characters": sum(len(b.text) for b in doc.blocks)}
    return doc


def document_from_abstract(title: str, abstract: str) -> Document:
    """Wrap an abstract as a one-section document so deep analysis can run (with warnings)."""
    doc = Document(source_path=None, source_type="abstract", title=title,
                   sha256=hashlib.sha256((abstract or "").encode("utf-8")).hexdigest(), extractor="abstract")
    if abstract:
        doc.blocks.append(Block(id="b0000", text=abstract, kind="paragraph"))
    assemble_sections(doc)
    for s in doc.sections:
        s.kind, s.title = "abstract", "Abstract"
    doc.warnings = ["ABSTRACT ONLY: no full text was ingested. Data, methodology, robustness and section-level "
                    "assessments cannot be verified; ingest the PDF with `paper-analyst ingest`."]
    return doc
