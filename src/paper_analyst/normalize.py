"""Identifier and title normalisation used for deduplication."""
from __future__ import annotations

import re
import unicodedata

_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
_ARXIV_OLD = re.compile(r"([a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?", re.IGNORECASE)


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = _DOI_PREFIX.sub("", doi.strip()).strip().lower()
    return doi or None


def normalize_arxiv_id(value: str | None) -> str | None:
    """Return a version-less arXiv id from an id, abs URL or DOI (10.48550/arXiv.X)."""
    if not value:
        return None
    value = value.strip()
    m = _ARXIV_NEW.search(value)
    if m:
        return m.group(1)
    m = _ARXIV_OLD.search(value)
    if m:
        return m.group(1).lower()
    return None


def normalize_title(title: str | None) -> str:
    """Lowercase, strip accents/punctuation/LaTeX and collapse whitespace."""
    if not title:
        return ""
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\$[^$]*\$", " ", text)  # inline LaTeX
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def normalize_whitespace(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
