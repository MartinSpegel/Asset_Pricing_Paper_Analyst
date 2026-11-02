"""PDF extraction tests.

Ground truth comes from the synthetic demo PDF (built by scripts/build_demo_pdf.py,
which records the page reportlab placed every paragraph on) and from small
programmatic fixtures. They validate extraction mechanics, not analysis accuracy.
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("reportlab")
import pdf_factory as F  # noqa: E402

from paper_analyst.fulltext import ExtractionError, extract_pdf, load_document  # noqa: E402
from paper_analyst.verify import canonical, find_span  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "sample_data" / "demo_paper.pdf"
GT = json.loads((ROOT / "sample_data" / "demo_paper.groundtruth.json").read_text())


@pytest.fixture(scope="module")
def demo_doc():
    return extract_pdf(DEMO)


def _locate(doc, text):
    hits = []
    for b in doc.blocks:
        span = find_span(b.text, text)
        if span:
            hits.append((b, span))
    return hits


def test_ground_truth_paragraphs_pages_sections_and_order(demo_doc):
    order = []
    for rec in GT["paragraphs"]:
        if rec["style"] in ("title",) or not rec["text"].strip():
            continue
        text = rec["text"].replace("Abstract. ", "Abstract. ")
        hits = _locate(demo_doc, text)
        assert len(hits) == 1, f"paragraph not found exactly once: {text[:60]!r} -> {len(hits)}"
        block, span = hits[0]
        page_start, _ = block.pages_for_span(*span)
        assert page_start == rec["page"], f"page mismatch for {text[:50]!r}"
        if rec["style"] not in ("heading", "authors"):
            sec = demo_doc.section_of(block)
            expected = rec["section"] or "Abstract"
            assert sec.label.replace("§", "") == expected or (rec["style"] == "abstract" and sec.kind == "abstract")
        order.append(demo_doc.blocks.index(block))
    assert order == sorted(order), "reading order differs from ground truth"


def test_headers_footers_and_page_numbers_removed(demo_doc):
    full = demo_doc.full_text()
    assert GT["header"] not in full
    reasons = {r["reason"] for r in demo_doc.removed_lines}
    assert reasons == {"running_header_footer", "page_number"}
    assert {b.printed_page for b in demo_doc.blocks} == {"1", "2"}


def test_structure_detected(demo_doc):
    kinds = [s.kind for s in demo_doc.sections]
    for k in ("abstract", "introduction", "literature", "theory", "data", "methodology", "results",
              "robustness", "conclusion", "references", "appendix"):
        assert k in kinds, k
    sub = next(s for s in demo_doc.sections if s.number == "5.1")
    assert sub.kind == "methodology" and sub.level == 2
    assert demo_doc.title.startswith("Transferring Pricing Kernels")
    assert demo_doc.page_layouts == {1: "mixed", 2: "two_column"}


def test_footnote_table_caption_and_cross_page_paragraph(demo_doc):
    note = [b for b in demo_doc.blocks if b.kind == "footnote"]
    assert len(note) == 1 and note[0].text.startswith("* Synthetic demonstration document")
    table = next(b for b in demo_doc.blocks if b.kind == "table")
    assert table.text.splitlines()[0] == "Model RMSE Sharpe t-stat"
    assert "Transferred SDF 0.86 0.94 2.9" in table.text
    cap = next(b for b in demo_doc.blocks if b.kind == "caption")
    assert cap.text == "Table 1: Out-of-sample pricing errors (synthetic illustration)"
    cross = next(b for b in demo_doc.blocks if b.text.startswith("We estimate the SDF weights"))
    assert (cross.page, cross.page_end) == (1, 2)
    span = find_span(cross.text, "using a feed-forward neural network with three hidden layers")
    assert cross.pages_for_span(*span) == (2, 2)
    # The footnote did not split the paragraph
    assert "implied by the pricing equation" in cross.text


def test_reference_entries_split(demo_doc):
    refs = demo_doc.blocks_of_kind("references")
    assert [b.text[:3] for b in refs if b.kind == "paragraph"] == ["[1]", "[2]", "[3]"]


def test_single_column_dehyphenation_and_headers(tmp_path):
    body = [("h", "1 Introduction"), ("p", "We study whether return predict-"),
            ("p", "ability is common across countries and how it relates to"),
            ("p", "the pricing kernel."), ("indent", "A new paragraph begins here after an indent."),
            ("h", "2 Data"), ("p", "Our sample covers 20 markets.")]
    path = F.single_column(tmp_path / "s.pdf", [body, [("p", "Second page text that is long enough to matter.")],
                                                 [("p", "Third page text that is also long enough.")]],
                           header="Running Header Text")
    doc = extract_pdf(path)
    assert doc.page_layouts[1] == "single"
    assert any("return predictability is common" in b.text for b in doc.blocks)
    assert doc.stats["dehyphenated"] >= 1
    assert not any("Running Header Text" in b.text for b in doc.blocks)
    intro = next(s for s in doc.sections if s.kind == "introduction")
    paras = [doc.block(i) for i in intro.block_ids if doc.block(i).kind == "paragraph"]
    assert len(paras) == 2 and paras[1].text.startswith("A new paragraph")


def test_two_column_reading_order(tmp_path):
    left = [f"Left column line {i:02d} with ordinary words in it." for i in range(12)]
    right = [f"Right column line {i:02d} with ordinary words." for i in range(12)]
    doc = extract_pdf(F.two_columns(tmp_path / "two.pdf", left, right))
    assert doc.page_layouts[1] == "two_column"
    text = doc.full_text()
    assert text.index("Left column line 11") < text.index("Right column line 00")
    # One paragraph flows from the bottom of the left column to the top of the right one.
    assert [b.column for b in doc.blocks] == [1]


def test_encrypted_pdf(tmp_path):
    path = F.encrypted(tmp_path / "enc.pdf", "secret")
    with pytest.raises(ExtractionError, match="encrypted"):
        extract_pdf(path)
    doc = extract_pdf(path, password="secret")
    assert "Confidential line 0" in doc.full_text()


def test_image_only_pdf_fails_explicitly(tmp_path):
    with pytest.raises(ExtractionError, match="no extractable text layer"):
        extract_pdf(F.image_only(tmp_path / "scan.pdf", pages=2))


def test_partial_text_layer_warns(tmp_path):
    doc = extract_pdf(F.text_then_image(tmp_path / "mixed.pdf"))
    assert doc.page_layouts[2] == "empty"
    assert any(w.startswith("Page 2: no text layer") for w in doc.warnings)
    assert any("No section headings" in w for w in doc.warnings)


def test_not_a_pdf_and_corrupt(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_text("hello")
    with pytest.raises(ExtractionError, match="not a PDF"):
        extract_pdf(bad)
    corrupt = tmp_path / "c.pdf"
    corrupt.write_bytes(b"%PDF-1.4\n" + b"\x00garbage" * 50)
    with pytest.raises(ExtractionError):
        extract_pdf(corrupt)
    with pytest.raises(ExtractionError, match="not found"):
        load_document(tmp_path / "missing.pdf")
    with pytest.raises(ExtractionError, match="Unsupported"):
        (tmp_path / "a.docx").write_text("x")
        load_document(tmp_path / "a.docx")


def test_document_roundtrip(demo_doc):
    from paper_analyst.fulltext import Document
    again = Document.from_dict(json.loads(json.dumps(demo_doc.to_dict())))
    assert [b.text for b in again.blocks] == [b.text for b in demo_doc.blocks]
    assert again.locator("b0016")["section"] == demo_doc.locator("b0016")["section"]


def test_extraction_is_deterministic(demo_doc):
    again = extract_pdf(DEMO)
    assert [canonical(b.text) for b in again.blocks] == [canonical(b.text) for b in demo_doc.blocks]


def test_regular_weight_allcaps_headings(tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    path = tmp_path / "caps.pdf"
    c = canvas.Canvas(str(path), pagesize=letter, invariant=1)
    y = 700
    for kind, text in [("h", "I. INTRODUCTION"), ("p", "We study pricing kernels across many equity markets today."),
                       ("p", "The question matters for international investors and for theory."),
                       ("h", "II. EMPIRICAL RESULTS"), ("p", "We find that pricing errors are lower for the model."),
                       ("p", "This sentence 3 countries is not a heading because it is a long body line.")]:
        c.setFont("Times-Roman", 10)
        if kind == "h":
            y -= 8
        c.drawString(72, y, text)
        y -= 21 if kind == "h" else 13
    c.showPage()
    c.save()
    doc = extract_pdf(path)
    assert [(s.number, s.kind) for s in doc.sections if s.heading_block] == [("I", "introduction"), ("II", "results")]
