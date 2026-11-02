"""Full-paper ingestion: PDF / plain-text extraction into a located, sectioned Document."""
from .model import Block, Document, ExtractionError, Section, SectionKind
from .pdf import extract_pdf
from .text import document_from_abstract, document_from_text


def load_document(path, **kwargs) -> Document:
    """Dispatch on file type (.pdf vs plain text / Markdown)."""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        raise ExtractionError(f"File not found: {p}")
    if p.suffix.lower() == ".pdf":
        return extract_pdf(p, **kwargs)
    if p.suffix.lower() in (".txt", ".md", ".text"):
        return document_from_text(p.read_text(encoding="utf-8"), source_path=str(p))
    with open(p, "rb") as fh:
        if fh.read(5) == b"%PDF-":
            return extract_pdf(p, **kwargs)
    raise ExtractionError(f"Unsupported file type: {p.suffix or '(none)'} (expected .pdf, .txt or .md)")


__all__ = ["Block", "Document", "ExtractionError", "Section", "SectionKind", "extract_pdf",
           "document_from_text", "document_from_abstract", "load_document"]
