"""arXiv Atom API (free, no key). https://info.arxiv.org/help/api/"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ..filters import SearchQuery, _date_key
from ..models import Paper
from ..normalize import normalize_arxiv_id, normalize_doi, normalize_whitespace
from .base import Source

BASE = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def parse_feed(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers = []
    for e in root.findall("a:entry", NS):
        abs_url = (e.findtext("a:id", default="", namespaces=NS) or "").strip()
        title = normalize_whitespace(e.findtext("a:title", default="", namespaces=NS))
        if not title or not abs_url:
            continue
        urls = {"landing": abs_url}
        for link in e.findall("a:link", NS):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                urls["pdf"] = link.get("href")
        published = (e.findtext("a:published", default="", namespaces=NS) or "")[:10] or None
        cats = [c.get("term") for c in e.findall("a:category", NS) if c.get("term")]
        journal = e.findtext("arxiv:journal_ref", default=None, namespaces=NS)
        papers.append(Paper(
            title=title,
            authors=[normalize_whitespace(a.findtext("a:name", default="", namespaces=NS))
                     for a in e.findall("a:author", NS)],
            abstract=normalize_whitespace(e.findtext("a:summary", default="", namespaces=NS)),
            publication_date=published,
            venue=normalize_whitespace(journal) if journal else "arXiv",
            doi=normalize_doi(e.findtext("arxiv:doi", default=None, namespaces=NS)),
            arxiv_id=normalize_arxiv_id(abs_url),
            urls=urls,
            sources=["arxiv"],
            topics=cats,
        ))
    return papers


def _quote(term: str) -> str:
    return f'"{term}"' if " " in term else term


class ArxivSource(Source):
    name = "arxiv"
    # Restrict to finance / econ / ML categories by default.
    DEFAULT_CATEGORIES = ["q-fin.*", "econ.EM", "econ.GN", "stat.ML", "cs.LG"]

    def __init__(self, transport, categories: list[str] | None = None):
        super().__init__(transport)
        self.categories = categories if categories is not None else self.DEFAULT_CATEGORIES

    def build_search_query(self, query: SearchQuery) -> str:
        parts = []
        terms = query.keywords or query.search_terms()
        if terms:
            joiner = " AND " if query.match_all_keywords else " OR "
            parts.append("(" + joiner.join(f"all:{_quote(t)}" for t in terms) + ")")
        if query.authors:
            parts.append("(" + " OR ".join(f"au:{_quote(a)}" for a in query.authors) + ")")
        if self.categories:
            parts.append("(" + " OR ".join(f"cat:{c}" for c in self.categories) + ")")
        if query.date_from or query.date_to:
            start = (_date_key(query.date_from) or "1991-01-01").replace("-", "") + "0000"
            end = (_date_key(query.date_to, end=True) or "2099-12-31").replace("-", "") + "2359"
            parts.append(f"submittedDate:[{start} TO {end}]")
        return " AND ".join(parts) or "cat:q-fin.*"

    def search(self, query: SearchQuery) -> list[Paper]:
        params = {
            "search_query": self.build_search_query(query),
            "start": 0,
            "max_results": min(query.limit, 100),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        return parse_feed(self.transport.get("arxiv", BASE, params))
