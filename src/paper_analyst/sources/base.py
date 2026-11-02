from __future__ import annotations

from abc import ABC, abstractmethod

from ..filters import SearchQuery
from ..http import Transport
from ..models import Paper


class Source(ABC):
    name: str = ""

    def __init__(self, transport: Transport):
        self.transport = transport

    @abstractmethod
    def search(self, query: SearchQuery) -> list[Paper]:
        """Query the API and return normalised papers (unfiltered beyond the API)."""
