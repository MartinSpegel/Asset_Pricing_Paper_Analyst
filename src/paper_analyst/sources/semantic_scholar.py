"""Semantic Scholar Graph API (free; optional key for higher limits).
https://api.semanticscholar.org/api-docs/graph"""
from __future__ import annotations

import os

from ..filters import SearchQuery, _date_key
from ..http import load_json
from ..models import Paper
from ..normalize import normalize_arxiv_id, normalize_doi, normalize_whitespace
from .base import Source

BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,authors,year,publicationDate,externalIds,url,venue,openAccessPdf,fieldsOfStudy"


def parse_paper(p: dict) -> Paper:
    ext = p.get("externalIds") or {}
    urls = {}
    if p.get("url"):
        urls["semantic_scholar"] = p["url"]
    pdf = (p.get("openAccessPdf") or {}).get("url")
    if pdf:
        urls["pdf"] = pdf
    arxiv = normalize_arxiv_id(ext.get("ArXiv"))
    if arxiv:
        urls.setdefault("landing", f"https://arxiv.org/abs/{arxiv}")
    return Paper(
        title=normalize_whitespace(p.get("title")),
        authors=[a.get("name") for a in p.get("authors") or [] if a.get("name")],
        abstract=normalize_whitespace(p.get("abstract")),
        publication_date=p.get("publicationDate") or (str(p["year"]) if p.get("year") else None),
        venue=p.get("venue") or None,
        doi=normalize_doi(ext.get("DOI")),
        arxiv_id=arxiv,
        s2_id=p.get("paperId"),
        urls=urls,
        sources=["semantic_scholar"],
        topics=list(p.get("fieldsOfStudy") or []),
    )


class SemanticScholarSource(Source):
    name = "semantic_scholar"

    def __init__(self, transport, api_key: str | None = None):
        super().__init__(transport)
        self.api_key = api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None

    def build_params(self, query: SearchQuery) -> dict:
        text = query.text_query()
        if query.authors:
            text = f"{text} {' '.join(query.authors)}".strip()
        params = {"query": text or "asset pricing", "fields": FIELDS, "limit": min(query.limit, 100)}
        if query.date_from or query.date_to:
            params["publicationDateOrYear"] = (
                f"{_date_key(query.date_from) or ''}:{_date_key(query.date_to, end=True) or ''}")
        return params

    def search(self, query: SearchQuery) -> list[Paper]:
        headers = {"x-api-key": self.api_key} if self.api_key else None
        data = load_json(self.transport.get("semantic_scholar", BASE, self.build_params(query), headers))
        return [parse_paper(p) for p in data.get("data", []) if p.get("title")]
