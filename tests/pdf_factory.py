"""Programmatic PDF fixtures with known layout, for extraction tests (requires reportlab).

These are mechanical test inputs (layout, failure modes), not papers.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

W, H = letter


def _c(path: Path, **kw) -> canvas.Canvas:
    return canvas.Canvas(str(path), pagesize=letter, invariant=1, **kw)


def single_column(path: Path, pages: list[list[tuple[str, str]]], header: str | None = None) -> Path:
    """pages: list of [(style, text_line)] with style in {"h", "p", "gap"}; one line per entry."""
    c = _c(path)
    for i, lines in enumerate(pages, 1):
        if header:
            c.setFont("Times-Italic", 8)
            c.drawCentredString(W / 2, H - 36, header)
            c.setFont("Times-Roman", 9)
            c.drawCentredString(W / 2, 30, str(i))
        y = H - 80
        for style, text in lines:
            if style == "gap":
                y -= 10
                continue
            if style == "h":
                y -= 6
                c.setFont("Times-Bold", 12)
            elif style == "indent":
                c.setFont("Times-Roman", 10)
                c.drawString(92, y, text)
                y -= 13
                continue
            else:
                c.setFont("Times-Roman", 10)
            c.drawString(72, y, text)
            y -= 16 if style == "h" else 13
        c.showPage()
    c.save()
    return path


def two_columns(path: Path, left: list[str], right: list[str], heading: str | None = None) -> Path:
    c = _c(path)
    y0 = H - 90
    if heading:
        c.setFont("Times-Bold", 12)
        c.drawString(72, y0 + 20, heading)
    c.setFont("Times-Roman", 10)
    for i, t in enumerate(left):
        c.drawString(72, y0 - 13 * i, t)
    for i, t in enumerate(right):
        c.drawString(W / 2 + 12, y0 - 13 * i, t)
    c.showPage()
    c.save()
    return path


def image_only(path: Path, pages: int = 1) -> Path:
    c = _c(path)
    for _ in range(pages):
        c.setFillGray(0.5)
        c.rect(72, 72, W - 144, H - 144, fill=1)   # vector graphic, no text layer
        c.showPage()
    c.save()
    return path


def text_then_image(path: Path) -> Path:
    c = _c(path)
    c.setFont("Times-Roman", 10)
    for i in range(30):
        c.drawString(72, H - 80 - 13 * i, f"This is line {i} of ordinary body text on the first page of the file.")
    c.showPage()
    c.setFillGray(0.5)
    c.rect(72, 72, W - 144, H - 144, fill=1)
    c.showPage()
    c.save()
    return path


def encrypted(path: Path, password: str = "secret") -> Path:
    from reportlab.lib import pdfencrypt
    enc = pdfencrypt.StandardEncryption(password, canPrint=1)
    c = canvas.Canvas(str(path), pagesize=letter, encrypt=enc)
    c.setFont("Times-Roman", 10)
    for i in range(30):
        c.drawString(72, H - 80 - 13 * i, f"Confidential line {i}: the sample covers stocks in many markets.")
    c.showPage()
    c.save()
    return path
