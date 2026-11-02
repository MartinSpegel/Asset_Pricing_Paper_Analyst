"""High-level orchestration: discover -> filter -> dedup -> rank -> store."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .dedup import deduplicate
from .filters import SearchQuery, apply_filters
from .http import HttpTransport, MockTransport, Transport
from .models import Paper
from .ranking import rank
from .sources import ALL_SOURCES
from .storage import Store

log = logging.getLogger(__name__)


@dataclass
class DiscoveryReport:
    fetched: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    after_filter: int = 0
    after_dedup: int = 0
    inserted: int = 0
    merged: int = 0
    papers: list[Paper] = field(default_factory=list)


def make_transport(offline: bool) -> Transport:
    return MockTransport() if offline else HttpTransport()


def discover(query: SearchQuery, sources: list[str] | None = None, transport: Transport | None = None,
             store: Store | None = None, offline: bool = False) -> DiscoveryReport:
    transport = transport or make_transport(offline)
    report = DiscoveryReport()
    collected: list[Paper] = []
    for name in sources or list(ALL_SOURCES):
        try:
            papers = ALL_SOURCES[name](transport).search(query)
            report.fetched[name] = len(papers)
            collected.extend(papers)
        except Exception as exc:  # one failing source must not break discovery
            log.warning("Source %s failed: %s", name, exc)
            report.errors[name] = str(exc)
    filtered = apply_filters(collected, query)
    report.after_filter = len(filtered)
    unique = rank(deduplicate(filtered))
    report.after_dedup = len(unique)
    if store is not None:
        for p in unique:
            pid, created = store.upsert(p)
            p.id = pid
            report.inserted += created
            report.merged += not created
    report.papers = unique
    return report
