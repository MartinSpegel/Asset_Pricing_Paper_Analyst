"""SQLite persistence with dedup-aware upserts."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .dedup import merge
from .models import Paper, ResearchStatus
from .normalize import normalize_arxiv_id, normalize_doi, normalize_title

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    norm_title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',
    abstract TEXT NOT NULL DEFAULT '',
    publication_date TEXT,
    venue TEXT,
    doi TEXT,
    arxiv_id TEXT,
    openalex_id TEXT,
    s2_id TEXT,
    urls TEXT NOT NULL DEFAULT '{}',
    sources TEXT NOT NULL DEFAULT '[]',
    topics TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'new',
    relevance_score REAL,
    relevance_breakdown TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_papers_doi ON papers(doi) WHERE doi IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_papers_arxiv ON papers(arxiv_id) WHERE arxiv_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_papers_norm_title ON papers(norm_title);
CREATE INDEX IF NOT EXISTS ix_papers_status ON papers(status);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    analyzer TEXT NOT NULL,
    model TEXT,
    memo_json TEXT NOT NULL,
    memo_markdown TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analyses_paper ON analyses(paper_id);
"""

_JSON_FIELDS = ("authors", "urls", "sources", "topics", "relevance_breakdown")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = "papers.db"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- papers -------------------------------------------------------
    @staticmethod
    def _row_to_paper(row: sqlite3.Row) -> Paper:
        d = dict(row)
        for f in _JSON_FIELDS:
            d[f] = json.loads(d[f]) if d[f] else ({} if f in ("urls", "relevance_breakdown") else [])
        for f in ("norm_title", "created_at", "updated_at"):
            d.pop(f, None)
        return Paper(**d)

    def find_existing(self, p: Paper) -> Paper | None:
        doi, ax, nt = normalize_doi(p.doi), normalize_arxiv_id(p.arxiv_id), normalize_title(p.title)
        for col, val in (("doi", doi), ("arxiv_id", ax)):
            if val:
                row = self.conn.execute(f"SELECT * FROM papers WHERE {col} = ?", (val,)).fetchone()
                if row:
                    return self._row_to_paper(row)
        if nt and len(nt) >= 15:
            row = self.conn.execute("SELECT * FROM papers WHERE norm_title = ?", (nt,)).fetchone()
            if row:
                return self._row_to_paper(row)
        return None

    def upsert(self, p: Paper) -> tuple[int, bool]:
        """Insert or merge a paper. Returns (id, created)."""
        p.doi, p.arxiv_id = normalize_doi(p.doi), normalize_arxiv_id(p.arxiv_id)
        existing = self.find_existing(p)
        if existing:
            merged = merge(existing, p)
            if p.relevance_score is not None:
                merged.relevance_score, merged.relevance_breakdown = p.relevance_score, p.relevance_breakdown
            self._write(merged, existing.id)
            return existing.id, False
        return self._write(p, None), True

    def _write(self, p: Paper, pid: int | None) -> int:
        vals = {
            "title": p.title, "norm_title": normalize_title(p.title),
            "authors": json.dumps(p.authors), "abstract": p.abstract or "",
            "publication_date": p.publication_date, "venue": p.venue, "doi": p.doi,
            "arxiv_id": p.arxiv_id, "openalex_id": p.openalex_id, "s2_id": p.s2_id,
            "urls": json.dumps(p.urls), "sources": json.dumps(sorted(set(p.sources))),
            "topics": json.dumps(p.topics), "status": p.status,
            "relevance_score": p.relevance_score,
            "relevance_breakdown": json.dumps(p.relevance_breakdown), "notes": p.notes or "",
            "updated_at": _now(),
        }
        with self.conn:
            if pid is None:
                vals["created_at"] = vals["updated_at"]
                cols = ", ".join(vals)
                cur = self.conn.execute(
                    f"INSERT INTO papers ({cols}) VALUES ({', '.join('?' * len(vals))})", list(vals.values()))
                return int(cur.lastrowid)
            sets = ", ".join(f"{k} = ?" for k in vals)
            self.conn.execute(f"UPDATE papers SET {sets} WHERE id = ?", [*vals.values(), pid])
            return pid

    def get(self, pid: int) -> Paper | None:
        row = self.conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone()
        return self._row_to_paper(row) if row else None

    def list(self, status: str | None = None, min_score: float | None = None,
             limit: int | None = None, order: str = "score") -> list[Paper]:
        sql, args = "SELECT * FROM papers WHERE 1=1", []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if min_score is not None:
            sql += " AND relevance_score >= ?"
            args.append(min_score)
        sql += {"score": " ORDER BY relevance_score IS NULL, relevance_score DESC, id",
                "date": " ORDER BY publication_date DESC, id",
                "id": " ORDER BY id"}[order]
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return [self._row_to_paper(r) for r in self.conn.execute(sql, args)]

    def set_status(self, pid: int, status: str) -> None:
        ResearchStatus(status)  # validate
        with self.conn:
            cur = self.conn.execute("UPDATE papers SET status = ?, updated_at = ? WHERE id = ?",
                                    (status, _now(), pid))
        if cur.rowcount == 0:
            raise KeyError(f"No paper with id {pid}")

    def set_notes(self, pid: int, notes: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE papers SET notes = ?, updated_at = ? WHERE id = ?", (notes, _now(), pid))

    def update_relevance(self, p: Paper) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE papers SET relevance_score = ?, relevance_breakdown = ?, updated_at = ? WHERE id = ?",
                (p.relevance_score, json.dumps(p.relevance_breakdown), _now(), p.id))

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    def status_counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.conn.execute("SELECT status, COUNT(*) FROM papers GROUP BY status")}

    # ---- analyses -----------------------------------------------------
    def save_analysis(self, pid: int, analyzer: str, model: str | None, memo_json: dict, markdown: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO analyses (paper_id, analyzer, model, memo_json, memo_markdown, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (pid, analyzer, model, json.dumps(memo_json), markdown, _now()))
        return int(cur.lastrowid)

    def latest_analysis(self, pid: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM analyses WHERE paper_id = ? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["memo_json"] = json.loads(d["memo_json"])
        return d
