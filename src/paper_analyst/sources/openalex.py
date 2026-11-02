"""OpenAlex works API (free, no key). https://docs.openalex.org"""
from __future__ import annotations

import os

from ..filters import SearchQuery, _date_key
from ..http import load_json
from ..models import Paper
from ..normalize import normalize_arxiv_id, normalize_doi, normalize_whitespace
from .base import Source

BASE = "https://api.openalex.org"


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    positions = [(pos, word) for word, poss in inverted_index.items() for pos in poss]
    return " ".join(word for _, word in sorted(positions))


def parse_work(w: dict) -> Paper:
    ids = w.get("ids") or {}
    primary = w.get("primary_location") or {}
    source = primary.get("source") or {}
    urls = {}
    if primary.get("landing_page_url"):
        urls["landing"] = primary["landing_page_url"]
    oa_url = (w.get("open_access") or {}).get("oa_url") or primary.get("pdf_url")
    if oa_url:
        urls["pdf"] = oa_url
    if w.get("id"):
        urls["openalex"] = w["id"]
    doi = normalize_doi(w.get("doi") or ids.get("doi"))
    arxiv = None
    for loc in w.get("locations") or []:
        u = loc.get("landing_page_url") or ""
        if "arxiv.org" in u:
            arxiv = normalize_arxiv_id(u)
    if doi and doi.startswith("10.48550/arxiv."):
        arxiv = arxiv or normalize_arxiv_id(doi)
    topics = [t.get("display_name") for t in (w.get("topics") or []) if t.get("display_name")]
    return Paper(
        title=normalize_whitespace(w.get("title") or w.get("display_name")),
        authors=[a["author"]["display_name"] for a in w.get("authorships") or []
                 if a.get("author", {}).get("display_name")],
        abstract=normalize_whitespace(reconstruct_abstract(w.get("abstract_inverted_index"))),
        publication_date=w.get("publication_date") or (str(w["publication_year"]) if w.get("publication_year") else None),
        venue=source.get("display_name"),
        doi=doi,
        arxiv_id=arxiv,
        openalex_id=(w.get("id") or "").rsplit("/", 1)[-1] or None,
        urls=urls,
        sources=["openalex"],
        topics=topics,
    )


class OpenAlexSource(Source):
    name = "openalex"

    def __init__(self, transport, mailto: str | None = None):
        super().__init__(transport)
        self.mailto = mailto or os.environ.get("OPENALEX_MAILTO") or None

    def _author_ids(self, name: str) -> list[str]:
        params = {"search": name, "per-page": 1}
        if self.mailto:
            params["mailto"] = self.mailto
        data = load_json(self.transport.get("openalex_authors", f"{BASE}/authors", params))
        return [r["id"].rsplit("/", 1)[-1] for r in data.get("results", [])[:1]]

    def build_params(self, query: SearchQuery, author_ids: list[str] | None = None) -> dict:
        filters = []
        if query.date_from:
            filters.append(f"from_publication_date:{_date_key(query.date_from)}")
        if query.date_to:
            filters.append(f"to_publication_date:{_date_key(query.date_to, end=True)}")
        if author_ids:
            filters.append("authorships.author.id:" + "|".join(author_ids))
        params = {"per-page": min(query.limit, 200), "sort": "relevance_score:desc"}
        text = query.text_query()
        if text:
            params["search"] = text
        else:
            params["sort"] = "publication_date:desc"
        if filters:
            params["filter"] = ",".join(filters)
        if self.mailto:
            params["mailto"] = self.mailto
        return params

    def search(self, query: SearchQuery) -> list[Paper]:
        author_ids: list[str] = []
        for a in query.authors:
            author_ids.extend(self._author_ids(a))
        params = self.build_params(query, author_ids)
        data = load_json(self.transport.get("openalex", f"{BASE}/works", params))
        return [parse_work(w) for w in data.get("results", []) if (w.get("title") or w.get("display_name"))]
