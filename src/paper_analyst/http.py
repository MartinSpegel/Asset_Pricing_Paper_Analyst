"""Tiny HTTP layer with a pluggable offline transport for mocked responses."""
from __future__ import annotations

import json
import time
from importlib import resources
from typing import Any, Protocol

import requests

USER_AGENT = "paper-analyst/0.1 (academic research tool)"


class Transport(Protocol):
    def get(self, source: str, url: str, params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None) -> str: ...


class HttpTransport:
    """Live HTTP transport with simple retry/backoff for 429/5xx."""

    def __init__(self, timeout: float = 30.0, retries: int = 3, backoff: float = 2.0):
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def get(self, source, url, params=None, headers=None) -> str:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(self.backoff * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as exc:  # network errors
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * (2 ** attempt))
        raise RuntimeError(f"{source}: request failed: {last_exc}")


MOCK_FILES = {
    "openalex": "openalex_works.json",
    "openalex_authors": "openalex_authors.json",
    "arxiv": "arxiv_query.xml",
    "semantic_scholar": "semantic_scholar_search.json",
}


class MockTransport:
    """Offline transport: returns bundled fixture responses, records requests."""

    def __init__(self, overrides: dict[str, str] | None = None):
        self.overrides = overrides or {}
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def get(self, source, url, params=None, headers=None) -> str:
        self.calls.append((source, url, params))
        if source in self.overrides:
            return self.overrides[source]
        name = MOCK_FILES[source]
        return resources.files("paper_analyst.mock_data").joinpath(name).read_text(encoding="utf-8")


def load_json(text: str) -> Any:
    return json.loads(text)
