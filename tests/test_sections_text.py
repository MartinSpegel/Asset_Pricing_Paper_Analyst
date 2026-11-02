from paper_analyst.fulltext import document_from_abstract, document_from_text
from paper_analyst.fulltext.sections import classify_heading, parse_heading

TEXT = """A Study of Pricing Kernels

Abstract
We study pricing kernels in 12 countries.

1 Introduction
We ask whether SDFs transfer across markets.

2 Model
The SDF is linear in factors.

3. Data and Sample
Our sample covers 1990 to 2020.

3.1 Variables
We define momentum as past returns.

4 Empirical Results
We find lower pricing errors.

5 Conclusion
Future research could extend this.

References
Placeholder reference.

A Proofs
Proof details here.
"""


def test_classify_heading():
    assert classify_heading("Introduction").value == "introduction"
    assert classify_heading("Related Literature").value == "literature"
    assert classify_heading("A Simple Model of Integration").value == "theory"
    assert classify_heading("Data and Sample Construction").value == "data"
    assert classify_heading("Empirical Strategy").value == "methodology"
    assert classify_heading("Main Results").value == "results"
    assert classify_heading("Robustness Checks").value == "robustness"
    assert classify_heading("Concluding Remarks").value == "conclusion"
    assert classify_heading("Online Appendix").value == "appendix"
    assert classify_heading("Acknowledgements") is None


def test_parse_heading():
    assert parse_heading("4.2 Out-of-Sample Tests") == ("4.2", "Out-of-Sample Tests")
    assert parse_heading("IV. EMPIRICAL RESULTS") == ("IV", "EMPIRICAL RESULTS")
    assert parse_heading("References") == (None, "References")
    assert parse_heading("3 countries are excluded because their data are incomplete and noisy in this sample.") is None
    assert parse_heading("12.5") is None


def test_text_document_sections_and_locators():
    doc = document_from_text(TEXT)
    kinds = [(s.number, s.kind) for s in doc.sections]
    assert (None, "abstract") in kinds
    assert ("3.1", "data") in kinds  # inherits parent kind via keyword "variables"
    assert ("A", "appendix") in kinds  # lettered section after references
    assert ("2", "theory") in kinds
    b = next(b for b in doc.blocks if b.text.startswith("We find lower"))
    loc = doc.locator(b.id)
    assert loc["page"] is None and loc["section"] == "§4 Empirical Results" and loc["paragraph"] == 1
    assert any("no page numbers" in w for w in doc.warnings)


def test_abstract_document():
    doc = document_from_abstract("T", "We study X.")
    assert doc.source_type == "abstract" and doc.sections[0].kind == "abstract"
    assert doc.warnings and "ABSTRACT ONLY" in doc.warnings[0]
