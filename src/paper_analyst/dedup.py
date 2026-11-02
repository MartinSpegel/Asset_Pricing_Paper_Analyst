"""Deduplicate papers by DOI, arXiv id and normalised title, merging metadata."""
from __future__ import annotations

from .models import Paper
from .normalize import normalize_arxiv_id, normalize_doi, normalize_title


def dedup_keys(p: Paper) -> list[str]:
    keys = []
    if doi := normalize_doi(p.doi):
        keys.append(f"doi:{doi}")
        if doi.startswith("10.48550/arxiv."):
            keys.append(f"arxiv:{normalize_arxiv_id(doi)}")
    if ax := normalize_arxiv_id(p.arxiv_id):
        keys.append(f"arxiv:{ax}")
    if (t := normalize_title(p.title)) and len(t) >= 15:  # avoid merging short generic titles
        keys.append(f"title:{t}")
    return keys


def merge(a: Paper, b: Paper) -> Paper:
    """Merge b into a (a wins on conflicts except where b is strictly richer)."""
    for attr in ("doi", "arxiv_id", "openalex_id", "s2_id", "venue", "publication_date"):
        if not getattr(a, attr) and getattr(b, attr):
            setattr(a, attr, getattr(b, attr))
    # Prefer a full date over a bare year.
    if a.publication_date and b.publication_date and len(b.publication_date) > len(a.publication_date):
        a.publication_date = b.publication_date
    # Prefer a published venue over "arXiv".
    if (a.venue or "").lower() == "arxiv" and b.venue and b.venue.lower() != "arxiv":
        a.venue = b.venue
    if len(b.abstract or "") > len(a.abstract or ""):
        a.abstract = b.abstract
    if len(b.authors) > len(a.authors):
        a.authors = list(b.authors)
    for k, v in b.urls.items():
        a.urls.setdefault(k, v)
    a.sources = sorted(set(a.sources) | set(b.sources))
    a.topics = list(dict.fromkeys(a.topics + b.topics))
    return a


def deduplicate(papers: list[Paper]) -> list[Paper]:
    """Merge records sharing any key; a record can bridge two earlier groups."""
    out: list[Paper | None] = []
    index: dict[str, int] = {}
    for p in papers:
        hits = sorted({index[k] for k in dedup_keys(p) if k in index})
        if not hits:
            out.append(p)
            target = len(out) - 1
        else:
            target = hits[0]
            merge(out[target], p)
            for other in hits[1:]:
                merge(out[target], out[other])
                out[other] = None
                for k, v in list(index.items()):
                    if v == other:
                        index[k] = target
        for k in dedup_keys(out[target]):
            index[k] = target
    return [p for p in out if p is not None]
