"""Paper discovery sources (all free APIs)."""
from .arxiv import ArxivSource
from .base import Source
from .openalex import OpenAlexSource
from .semantic_scholar import SemanticScholarSource

ALL_SOURCES = {
    "openalex": OpenAlexSource,
    "arxiv": ArxivSource,
    "semantic_scholar": SemanticScholarSource,
}

__all__ = ["Source", "OpenAlexSource", "ArxivSource", "SemanticScholarSource", "ALL_SOURCES"]
