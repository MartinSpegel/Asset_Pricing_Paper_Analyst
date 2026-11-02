"""Core data structures."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResearchStatus(str, Enum):
    NEW = "new"
    SCREENING = "screening"
    TO_READ = "to_read"
    READING = "reading"
    ANALYZED = "analyzed"
    ARCHIVED = "archived"
    REJECTED = "rejected"


@dataclass
class Paper:
    """Normalised paper metadata, independent of the source API."""

    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    publication_date: str | None = None  # ISO "YYYY-MM-DD" or "YYYY"
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    urls: dict[str, str] = field(default_factory=dict)  # e.g. {"landing": ..., "pdf": ...}
    sources: list[str] = field(default_factory=list)  # e.g. ["openalex", "arxiv"]
    topics: list[str] = field(default_factory=list)  # source-provided topic labels / categories
    # Populated locally
    id: int | None = None
    status: str = ResearchStatus.NEW.value
    relevance_score: float | None = None
    relevance_breakdown: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def year(self) -> int | None:
        if self.publication_date and self.publication_date[:4].isdigit():
            return int(self.publication_date[:4])
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
