"""PDF text extraction with layout reconstruction.

Pipeline per page (pdfplumber/pdfminer word boxes):
  words -> rows (same baseline) -> fragments (split at wide horizontal gaps)
  -> drop running headers/footers and page numbers (recorded, not silently lost)
  -> detect a two-column gutter and order fragments (full-width regions, then
     left column, then right column)
  -> classify lines (heading / caption / table / footnote / body)
  -> merge lines into paragraphs (spacing, indentation, short last lines),
     de-hyphenating line breaks and recording page offsets.

Failure handling is explicit: unreadable, encrypted and image-only PDFs raise
``ExtractionError``; partial problems (pages without a text layer, garbled
font encodings, ambiguous layouts, missing headings) become ``warnings`` on the
``Document``. No text is ever generated to fill a gap.
"""
from __future__ import annotations

import hashlib
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .model import Block, Document, ExtractionError
from .sections import assemble_sections, parse_heading

LAYOUT_VERSION = "layout-v1"
_BOLD = re.compile(r"(bold|black|heavy|semibold|demi)", re.IGNORECASE)
_PAGE_NUM = re.compile(r"^(page\s+)?(\d{1,4}|[ivxlc]{1,6})(\s+(of|/)\s+\d{1,4})?$|^[-–]\s*\d{1,4}\s*[-–]$", re.IGNORECASE)
_CAPTION = re.compile(r"^(table|figure|fig\.|exhibit)\s+[A-Z]?\d+[A-Za-z]?(\.\d+)?\s*[:.\u2013\u2014-]", re.IGNORECASE)
_CAPTION_LOOSE = re.compile(r"^(table|figure|fig\.|exhibit)\s+[A-Z]?\d+[A-Za-z]?\b", re.IGNORECASE)
_NUMERIC_TOKEN = re.compile(r"^[(\[]?[-−–+]?\$?\d[\d,]*\.?\d*%?[)\]]?\**$|^[-−–]?\.\d+\**$|^\(?[-−–]?\d*\.\d+\)?\**$")


@dataclass
class Frag:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: bool
    page: int
    kind: str = "body"     # body | heading | caption | table | footnote | title
    column: int = 0
    n_words: int = 0


@dataclass
class PageData:
    number: int
    width: float
    height: float
    frags: list[Frag] = field(default_factory=list)
    has_images: bool = False
    printed_label: str | None = None
    layout: str = "single"
    gutter: float | None = None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # ligatures (ﬁ -> fi), full-width chars
    return text.replace("­", "").replace("−", "-")


def _page_fragments(page, number: int) -> PageData:
    pd = PageData(number=number, width=float(page.width), height=float(page.height),
                  has_images=bool(page.images))
    words = page.extract_words(extra_attrs=["size", "fontname"], x_tolerance=1.5, y_tolerance=2.5,
                               keep_blank_chars=False, use_text_flow=False)
    words = [w for w in words if w["text"].strip()]
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(w["top"] - rows[-1][0]["top"]) <= 2.5:
            rows[-1].append(w)
        else:
            rows.append([w])
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        current: list[dict] = [row[0]]
        for w in row[1:]:
            size = max(current[-1]["size"], 6.0)
            if w["x0"] - current[-1]["x1"] > 1.5 * size:
                pd.frags.append(_make_frag(current, number))
                current = [w]
            else:
                current.append(w)
        pd.frags.append(_make_frag(current, number))
    return pd


def _make_frag(words: list[dict], page: int) -> Frag:
    text = _norm(" ".join(w["text"] for w in words))
    chars = sum(len(w["text"]) for w in words)
    bold_chars = sum(len(w["text"]) for w in words if _BOLD.search(w.get("fontname", "")))
    return Frag(text=text, x0=min(w["x0"] for w in words), x1=max(w["x1"] for w in words),
                top=min(w["top"] for w in words), bottom=max(w["bottom"] for w in words),
                size=statistics.median(w["size"] for w in words), bold=bold_chars >= 0.8 * chars,
                page=page, n_words=len(words))


def _body_size(pages: list[PageData]) -> float:
    c: Counter = Counter()
    for p in pages:
        for f in p.frags:
            c[round(f.size * 2) / 2] += len(f.text)
    return c.most_common(1)[0][0] if c else 10.0


def _strip_margins(pages: list[PageData], doc: Document, margin: float) -> None:
    """Remove running headers/footers (repeated across pages) and page-number lines."""
    def key(t: str) -> str:
        return re.sub(r"\d+", "#", t.lower()).strip()

    in_margin = []
    for p in pages:
        for f in p.frags:
            if f.top < p.height * margin or f.bottom > p.height * (1 - margin):
                in_margin.append((p, f))
    counts = Counter(key(f.text) for _, f in in_margin)
    n_pages = len(pages)
    for p, f in in_margin:
        t = f.text.strip()
        reason = None
        if _PAGE_NUM.match(t):
            reason = "page_number"
            m = re.search(r"\d{1,4}|[ivxlc]{1,6}", t, re.IGNORECASE)
            p.printed_label = p.printed_label or (m.group(0) if m else None)
        elif n_pages >= 2 and counts[key(t)] >= max(2, int(0.5 * n_pages)):
            reason = "running_header_footer"
        if reason:
            p.frags.remove(f)
            doc.removed_lines.append({"page": p.number, "text": t, "reason": reason})


def _detect_columns(p: PageData) -> None:
    frags = p.frags
    if len(frags) < 8:
        return
    best = None
    for x in range(int(p.width * 0.3), int(p.width * 0.7), 2):
        left = [f for f in frags if f.x1 <= x]
        right = [f for f in frags if f.x0 >= x]
        crossing = len(frags) - len(left) - len(right)
        if len(left) < 3 or len(right) < 3:
            continue
        cand = (crossing, -min(len(left), len(right)), x)
        if best is None or cand < best:
            best = cand
    if best is None:
        return
    crossing, _, x = best
    left = [f for f in frags if f.x1 <= x]
    right = [f for f in frags if f.x0 >= x]
    if len(left) + len(right) < 0.4 * len(frags):
        return
    # Right-column text should share a common left edge (rules out tables).
    edges = Counter(round(f.x0 / 3) for f in right)
    aligned = edges.most_common(1)[0][1] / len(right)
    if aligned < 0.6:
        return
    # Refine: put the gutter in the middle of the empty band.
    lo = max(f.x1 for f in left)
    hi = min(f.x0 for f in right)
    p.gutter = (lo + hi) / 2 if hi > lo else float(x)
    p.layout = "two_column" if crossing == 0 else "mixed"


def _order(p: PageData) -> list[Frag]:
    frags = sorted(p.frags, key=lambda f: (f.top, f.x0))
    if p.gutter is None:
        return frags
    g = p.gutter
    out: list[Frag] = []
    region: list[Frag] = []

    def flush():
        left = [f for f in region if f.x1 <= g]
        right = [f for f in region if f.x0 >= g]
        for f in left:
            f.column = 1
        for f in right:
            f.column = 2
        out.extend(sorted(left, key=lambda f: f.top) + sorted(right, key=lambda f: f.top))
        region.clear()

    last_span: Frag | None = None
    for f in frags:
        spanning = f.x0 < g - 1 and f.x1 > g + 1
        # Short last line of a full-width paragraph does not cross the gutter but belongs to it.
        if not spanning and last_span is not None and abs(f.x0 - last_span.x0) < 3 \
                and 0 <= f.top - last_span.bottom < 0.6 * f.size:
            spanning = True
        if spanning:
            flush()
            out.append(f)
            last_span = f
        else:
            region.append(f)
            last_span = None
    flush()
    return out


def _is_table_line(text: str) -> bool:
    toks = text.split()
    numeric = sum(bool(_NUMERIC_TOKEN.match(t)) for t in toks)
    return len(toks) >= 3 and numeric >= 3 and numeric >= 0.6 * len(toks)


def _plain_heading(t: str, nxt: "Frag | None", f: "Frag", body: float) -> bool:
    """Regular-weight heading: numbered (or a canonical name), all-caps or short, and followed by a gap."""
    parsed = parse_heading(t)
    if parsed is None:
        return False
    number, title = parsed
    gap_after = (nxt.top - f.bottom) if nxt is not None and nxt.column == f.column and nxt.top > f.top else 99
    styled = title.isupper() or bool(number and re.fullmatch(r"[IVX]+", number)) or number is None
    return styled and gap_after > 0.35 * body and len(t.split()) <= 8


def _classify(frags: list[Frag], p: PageData, body: float) -> None:
    # Rows split into >= 3 cells within one column are table rows (cells were split at wide gaps).
    rows: dict[tuple[int, int], list[Frag]] = {}
    for f in frags:
        rows.setdefault((f.column, round(f.top / 2.5)), []).append(f)
    table_rows = {id(f) for row in rows.values() if len(row) >= 3 for f in row}
    caption_open: Frag | None = None
    for i, f in enumerate(frags):
        t = f.text.strip()
        prev = frags[i - 1] if i else None
        gap_before = (f.top - prev.bottom) if prev and prev.column == f.column and f.top > prev.top else 99
        big = f.size >= body * 1.08
        standalone = gap_before > 0.35 * body or prev is None
        if caption_open is not None and prev is caption_open and f.column == prev.column \
                and 0 <= gap_before < 0.5 * body and abs(f.size - prev.size) < 0.5 and id(f) not in table_rows:
            f.kind = "caption"  # continuation line of a caption
        elif id(f) in table_rows:
            f.kind = "table"
        elif p.number == 1 and f.size >= body * 1.3 and f.top < p.height * 0.35 and not parse_heading(t):
            f.kind = "title"
        elif _CAPTION.match(t) or (_CAPTION_LOOSE.match(t) and (f.bold or abs(f.size - body) >= 0.75)):
            f.kind = "caption"
        elif (f.bold or big) and standalone and len(t.split()) <= 14 and not t.endswith((",", ";")) \
                and (parse_heading(t) is not None or (t[:1].isupper() and not t.endswith(".") and f.bold)):
            f.kind = "heading"
        elif standalone and _plain_heading(t, frags[i + 1] if i + 1 < len(frags) else None, f, body):
            f.kind = "heading"  # e.g. journal styles with small-caps / regular-weight headings
        elif f.size <= body * 0.88 and f.top > p.height * 0.6 and not _is_table_line(t):
            f.kind = "footnote"
        elif _is_table_line(t):
            f.kind = "table"
        caption_open = f if f.kind == "caption" else None


def _column_geometry(frags: list[Frag]) -> dict[tuple[int, int], tuple[float, float]]:
    """(page, column) -> (typical left edge, right edge) of body text."""
    lefts: dict[tuple[int, int], Counter] = {}
    rights: dict[tuple[int, int], list[float]] = {}
    for f in frags:
        if f.kind != "body":
            continue
        k = (f.page, f.column)
        lefts.setdefault(k, Counter())[round(f.x0)] += 1
        rights.setdefault(k, []).append(f.x1)
    return {k: (lefts[k].most_common(1)[0][0], max(rights[k])) for k in lefts}


def _merge(frags: list[Frag], body: float, doc: Document) -> list[Block]:
    """Merge lines into blocks. Footnotes are kept out of the main text flow so a
    paragraph interrupted by a footnote (or page break) stays one block."""
    blocks: list[Block] = []
    pending_notes: list[dict] = []
    geom = _column_geometry(frags)
    stats = doc.stats

    def emit(c: dict) -> None:
        if c and c["text"].strip():
            blocks.append(Block(id=f"b{len(blocks):04d}", text=c["text"].strip(), kind=c["kind"],
                                page=c["page"], page_end=c["page_end"], column=c["column"],
                                bbox=(c["x0"], c["top"], c["x1"], c["bottom"]), page_offsets=c["offsets"]))

    def start(f: Frag, kind: str) -> dict:
        return {"text": "", "kind": kind, "page": f.page, "page_end": f.page, "column": f.column,
                "x0": f.x0, "top": f.top, "x1": f.x1, "bottom": f.bottom, "offsets": [[0, f.page]],
                "last": None}

    def append(c: dict, f: Frag) -> None:
        text = f.text.strip()
        last: Frag | None = c["last"]
        if c["text"]:
            if c["page_end"] != f.page:
                c["offsets"].append([len(c["text"]) + 1, f.page])
                c["page_end"] = f.page
            if c["kind"] == "table":
                c["text"] += (" " if last and abs(last.top - f.top) <= 2.5 else "\n") + text
            elif re.search(r"[A-Za-z]-$", c["text"]) and text[:1].islower():
                c["text"] = c["text"][:-1] + text  # de-hyphenate a line break
                stats["dehyphenated"] = stats.get("dehyphenated", 0) + 1
            else:
                c["text"] += " " + text
        else:
            c["text"] = text
        if f.page == c["page"]:
            c["x0"], c["x1"] = min(c["x0"], f.x0), max(c["x1"], f.x1)
            c["top"], c["bottom"] = min(c["top"], f.top), max(c["bottom"], f.bottom)
        c["last"] = f

    cur: dict | None = None
    for f in frags:
        kind = {"body": "paragraph"}.get(f.kind, f.kind)
        if kind == "footnote":
            note = pending_notes[-1] if pending_notes and pending_notes[-1]["page"] == f.page else None
            if note is None or (f.top - note["last"].bottom) > 0.6 * body:
                note = start(f, "footnote")
                pending_notes.append(note)
            append(note, f)
            continue
        new = cur is None or kind == "heading" or cur["kind"] == "heading" or cur["kind"] != kind
        if not new and re.match(r"^(\[\d{1,3}\]|\d{1,3}\.\s)", f.text.strip()):
            new = True                           # numbered list / reference entry
        prev: Frag | None = cur["last"] if cur else None
        if not new and prev is not None and kind in ("paragraph", "caption"):
            same_flow = prev.page == f.page and prev.column == f.column and f.top >= prev.top
            left, _ = geom.get((f.page, f.column), (f.x0, f.x1))
            _, prev_right = geom.get((prev.page, prev.column), (prev.x0, prev.x1))
            if same_flow and (f.top - prev.bottom) > 0.75 * body:
                new = True                       # vertical paragraph spacing
            elif kind == "paragraph" and f.x0 > left + 0.8 * body:
                new = True                       # first-line indent
            elif prev.text.rstrip().endswith((".", "?", "!", ":")) and prev.x1 < prev_right - 2.5 * body:
                new = True                       # short last line of previous paragraph
            elif same_flow and abs(f.size - prev.size) > 1.0:
                new = True
        if new:
            if cur is not None:
                emit(cur)
                for n in pending_notes:
                    emit(n)
                pending_notes.clear()
            cur = start(f, kind)
        append(cur, f)
    if cur is not None:
        emit(cur)
    for n in pending_notes:
        emit(n)
    return blocks


def _password_error(exc: BaseException) -> bool:
    from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
    seen: list = [exc, exc.__cause__, exc.__context__, *getattr(exc, "args", ())]
    return any(isinstance(e, (PDFPasswordIncorrect, PDFEncryptionError)) for e in seen)


def extract_pdf(path: str | Path, password: str | None = None, margin: float = 0.07) -> Document:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("pdfplumber is required for PDF ingestion: pip install pdfplumber") from exc

    path = Path(path)
    if not path.exists():
        raise ExtractionError(f"File not found: {path}")
    data = path.read_bytes()
    if not data.lstrip()[:5] == b"%PDF-":
        raise ExtractionError(f"{path.name} is not a PDF file (missing %PDF header).")
    doc = Document(source_path=str(path), source_type="pdf", sha256=hashlib.sha256(data).hexdigest(),
                   extractor=f"pdfplumber {pdfplumber.__version__} + {LAYOUT_VERSION}")
    try:
        pdf = pdfplumber.open(str(path), password=password or "")
    except Exception as exc:
        if _password_error(exc):
            raise ExtractionError(f"{path.name} is encrypted; supply the correct password (--password).") from exc
        raise ExtractionError(f"Could not open {path.name}: {type(exc).__name__}: {exc}") from exc

    with pdf:
        try:
            pages = [_page_fragments(pg, i + 1) for i, pg in enumerate(pdf.pages)]
            meta = pdf.metadata or {}
        except Exception as exc:
            if _password_error(exc):
                raise ExtractionError(f"{path.name} is encrypted; supply the correct password (--password).") from exc
            raise ExtractionError(f"Failed to parse {path.name}: {type(exc).__name__}: {exc}") from exc

    doc.num_pages = len(pages)
    if not pages:
        raise ExtractionError(f"{path.name} contains no pages.")
    empty = [p.number for p in pages if not p.frags]
    if len(empty) == len(pages):
        raise ExtractionError(
            f"{path.name} has no extractable text layer on any page (likely a scanned/image-only PDF). "
            "OCR is not performed; run e.g. `ocrmypdf` first.")
    for p in pages:
        if not p.frags:
            p.layout = "empty"
            doc.warnings.append(f"Page {p.number}: no text layer"
                                + (" (image-only page; OCR not performed)." if p.has_images else " (blank page)."))
    for p in pages:
        text = " ".join(f.text for f in p.frags)
        bad = text.count("(cid:") + text.count("�")
        if text and bad / max(1, len(text.split())) > 0.05:
            doc.warnings.append(f"Page {p.number}: text appears garbled (font-encoding problems); "
                                "quotes from this page may be unreliable.")

    body = _body_size(pages)
    _strip_margins(pages, doc, margin)
    ordered: list[Frag] = []
    for p in pages:
        _detect_columns(p)
        doc.page_layouts[p.number] = p.layout if p.frags else "empty"
        if p.layout == "mixed":
            doc.warnings.append(f"Page {p.number}: full-width elements (title, abstract, wide tables or figures) "
                                "inside a two-column layout; reading order was reconstructed around them.")
        frs = _order(p)
        _classify(frs, p, body)
        ordered.extend(frs)

    title_frags = [f for f in ordered if f.kind == "title"]
    meta_title = (meta.get("Title") or "").strip() if isinstance(meta.get("Title"), str) else ""
    if meta_title and not re.match(r"^(untitled|microsoft word|\S+\.(docx?|tex|pdf))", meta_title, re.IGNORECASE):
        doc.title = _norm(meta_title)
    elif title_frags:
        doc.title = " ".join(f.text for f in title_frags)

    doc.blocks = _merge(ordered, body, doc)
    labels = {p.number: p.printed_label for p in pages}
    for b in doc.blocks:
        b.printed_page = labels.get(b.page)
    assemble_sections(doc)
    doc.stats.update({
        "body_font_size": body, "pages": len(pages), "blocks": len(doc.blocks),
        "characters": sum(len(b.text) for b in doc.blocks),
        "two_column_pages": sum(1 for v in doc.page_layouts.values() if v in ("two_column", "mixed")),
        "removed_margin_lines": len(doc.removed_lines),
    })
    if doc.stats["characters"] < 2000:
        doc.warnings.append("Very little text was extracted (<2000 characters); the PDF may be incomplete.")
    return doc
