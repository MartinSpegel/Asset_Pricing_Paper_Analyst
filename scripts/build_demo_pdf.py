"""Build the SYNTHETIC two-column demonstration PDF and its ground-truth JSON.

    python scripts/build_demo_pdf.py [--out sample_data]

Produces ``demo_paper.pdf`` (two-column body, full-width title/abstract, running
header, page numbers, footnote, table, references and appendix) and
``demo_paper.groundtruth.json`` recording, for every text flowable, its exact
text, style, section and the page reportlab placed it on. Tests compare the
extractor's output with this ground truth.

Requires reportlab (``pip install -e ".[dev]"``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, FrameBreak, NextPageTemplate, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

sys.path.insert(0, str(Path(__file__).parent))
import demo_paper_content as C  # noqa: E402

HEADER = "Synthetic Demonstration Paper - paper-analyst test fixture"
BODY = ParagraphStyle("body", fontName="Times-Roman", fontSize=10, leading=12.5, alignment=4,
                      spaceAfter=0, firstLineIndent=12)
BODY_FIRST = ParagraphStyle("body_first", parent=BODY, firstLineIndent=0)
HEAD = ParagraphStyle("heading", fontName="Times-Bold", fontSize=11.5, leading=14, spaceBefore=10, spaceAfter=4)
TITLE = ParagraphStyle("title", fontName="Times-Bold", fontSize=17, leading=21, alignment=1, spaceAfter=8)
AUTH = ParagraphStyle("authors", fontName="Times-Roman", fontSize=11, leading=14, alignment=1, spaceAfter=10)
ABS = ParagraphStyle("abstract", fontName="Times-Roman", fontSize=10, leading=12.5, alignment=4,
                     leftIndent=36, rightIndent=36, spaceAfter=6)
REF = ParagraphStyle("reference", parent=BODY_FIRST, fontSize=9, leading=11, spaceAfter=3)
CAP = ParagraphStyle("caption", fontName="Times-Bold", fontSize=9, leading=11, spaceBefore=6, spaceAfter=3)


class Doc(BaseDocTemplate):
    def __init__(self, path, **kw):
        super().__init__(path, pagesize=letter, title=C.TITLE, author="synthetic", **kw)
        self.records: list[dict] = []
        self.current_section = None

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            text = flowable.getPlainText()
            style = flowable.style.name
            if style == "heading":
                self.current_section = text
            self.records.append({"text": text, "style": style, "page": self.page,
                                 "section": self.current_section})


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Italic", 8.5)
    canvas.drawCentredString(letter[0] / 2, letter[1] - 0.5 * inch, HEADER)
    canvas.setFont("Times-Roman", 9)
    canvas.drawCentredString(letter[0] / 2, 0.45 * inch, str(doc.page))
    if doc.page == 1:
        canvas.setFont("Times-Roman", 7.5)
        canvas.drawString(0.9 * inch, 0.95 * inch, C.FOOTNOTE)
    canvas.restoreState()


def build(out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path, gt_path = out_dir / "demo_paper.pdf", out_dir / "demo_paper.groundtruth.json"
    doc = Doc(str(pdf_path), invariant=1)  # invariant=1 -> byte-reproducible output
    W, H = letter
    m, gap = 0.9 * inch, 0.3 * inch
    colw = (W - 2 * m - gap) / 2
    top_h = 3.0 * inch
    body_top, body_bottom = H - 0.75 * inch, 1.2 * inch
    first = PageTemplate("first", onPage=_header_footer, frames=[
        Frame(m, body_top - top_h, W - 2 * m, top_h, id="top"),
        Frame(m, body_bottom, colw, body_top - top_h - body_bottom, id="l1"),
        Frame(m + colw + gap, body_bottom, colw, body_top - top_h - body_bottom, id="r1")])
    later = PageTemplate("later", onPage=_header_footer, frames=[
        Frame(m, 0.8 * inch, colw, body_top - 0.8 * inch, id="l"),
        Frame(m + colw + gap, 0.8 * inch, colw, body_top - 0.8 * inch, id="r")])
    doc.addPageTemplates([first, later])

    story = [Paragraph(C.TITLE, TITLE), Paragraph(C.AUTHORS, AUTH),
             Paragraph("<b>Abstract.</b> " + C.ABSTRACT, ABS), NextPageTemplate("later"), FrameBreak()]
    for heading, paras in C.SECTIONS:
        story.append(Paragraph(heading, HEAD))
        for i, para in enumerate(paras):
            style = REF if heading == "References" else (BODY_FIRST if i == 0 else BODY)
            story.append(Paragraph(para, style))
        if heading.startswith("6 "):
            story.append(Paragraph(C.TABLE_CAPTION, CAP))
            t = Table(C.TABLE_ROWS, colWidths=[colw * 0.4] + [colw * 0.2] * 3)
            t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Times-Roman", 9),
                                   ("FONT", (0, 0), (-1, 0), "Times-Bold", 9),
                                   ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                                   ("LINEABOVE", (0, 0), (-1, 0), 0.5, "black"),
                                   ("LINEBELOW", (0, 0), (-1, 0), 0.5, "black"),
                                   ("LINEBELOW", (0, -1), (-1, -1), 0.5, "black")]))
            story += [t, Spacer(1, 6)]
    doc.build(story)
    gt = {"title": C.TITLE, "synthetic": True, "header": HEADER, "footnote": C.FOOTNOTE,
          "num_pages": doc.page, "paragraphs": doc.records}
    gt_path.write_text(json.dumps(gt, indent=1) + "\n", encoding="utf-8")
    return pdf_path, gt_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "sample_data"))
    paths = build(Path(ap.parse_args().out))
    print("wrote", *paths)
