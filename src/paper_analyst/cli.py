"""Command-line interface: ``paper-analyst --help``."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .analysis import get_analyzer
from .export import export_obsidian, render_memo
from .filters import TOPIC_PRESETS, SearchQuery
from .memo import ResearchMemo
from .models import ResearchStatus
from .pipeline import discover
from .ranking import rank
from .sources import ALL_SOURCES
from .storage import Store

DEMO_QUERY = SearchQuery(
    keywords=[], topics=["sdf", "return_predictability", "transfer_learning", "international_asset_pricing"],
    date_from="2018", limit=25)


def _env_offline() -> bool:
    return os.environ.get("PAPER_ANALYST_OFFLINE", "0").lower() in ("1", "true", "yes")


def _store(args) -> Store:
    return Store(args.db or os.environ.get("PAPER_ANALYST_DB", "papers.db"))


def _print_table(papers) -> None:
    if not papers:
        print("(no papers)")
        return
    print(f"{'ID':>4}  {'Score':>5}  {'Year':>4}  {'Status':<9}  {'Sources':<28}  Title")
    for p in papers:
        score = f"{p.relevance_score:5.1f}" if p.relevance_score is not None else "    -"
        print(f"{p.id or '-':>4}  {score}  {p.year or '':>4}  {p.status:<9}  "
              f"{','.join(p.sources)[:28]:<28}  {p.title[:80]}")


# ---- commands --------------------------------------------------------------
def cmd_discover(args) -> int:
    q = SearchQuery(keywords=args.keyword or [], authors=args.author or [], topics=args.topic or [],
                    date_from=args.date_from, date_to=args.date_to, limit=args.limit,
                    match_all_keywords=args.all)
    if not (q.keywords or q.authors or q.topics):
        print("Provide at least one --keyword, --author or --topic.", file=sys.stderr)
        return 2
    offline = args.offline or _env_offline()
    with _store(args) as store:
        rep = discover(q, sources=args.source, store=store, offline=offline)
    mode = "OFFLINE (mocked responses)" if offline else "live APIs"
    print(f"Discovery via {mode}")
    for src, n in rep.fetched.items():
        print(f"  {src:<17} {n:>3} results")
    for src, err in rep.errors.items():
        print(f"  {src:<17} ERROR: {err}")
    print(f"  after filters: {rep.after_filter}, after dedup: {rep.after_dedup}, "
          f"new in DB: {rep.inserted}, merged into existing: {rep.merged}")
    _print_table(rep.papers)
    return 0


def cmd_list(args) -> int:
    with _store(args) as store:
        _print_table(store.list(status=args.status, min_score=args.min_score, limit=args.limit, order=args.order))
    return 0


def cmd_show(args) -> int:
    with _store(args) as store:
        p = store.get(args.id)
        if not p:
            print(f"No paper with id {args.id}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(p.to_dict(), indent=2, ensure_ascii=False))
        else:
            a = store.latest_analysis(p.id)
            memo = ResearchMemo.from_dict(a["memo_json"]) if a else None
            print(render_memo(p, memo))
    return 0


def cmd_rank(args) -> int:
    with _store(args) as store:
        papers = rank(store.list(order="id"))
        for p in papers:
            store.update_relevance(p)
        _print_table(papers[: args.limit] if args.limit else papers)
    return 0


def cmd_status(args) -> int:
    with _store(args) as store:
        if args.id is None:
            for s, n in sorted(store.status_counts().items()):
                print(f"{s:<10} {n}")
            print(f"{'total':<10} {store.count()}")
            return 0
        try:
            store.set_status(args.id, args.set)
        except (KeyError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.notes is not None:
            store.set_notes(args.id, args.notes)
        print(f"Paper {args.id} -> {args.set}")
    return 0


def _analyze_one(store, analyzer, pid: int, text_file: str | None, out_dir: str | None) -> int:
    p = store.get(pid)
    if not p:
        print(f"No paper with id {pid}", file=sys.stderr)
        return 1
    full_text = Path(text_file).read_text(encoding="utf-8") if text_file else None
    memo = analyzer.analyze(p, full_text=full_text)
    if p.status in (ResearchStatus.NEW.value, ResearchStatus.SCREENING.value, ResearchStatus.TO_READ.value):
        store.set_status(p.id, ResearchStatus.ANALYZED.value)
        p.status = ResearchStatus.ANALYZED.value
    md = render_memo(p, memo)
    store.save_analysis(p.id, memo.analyzer, memo.model, memo.to_dict(), md)
    n_claims = sum(len(s.claims) for s in memo.sections.values())
    print(f"[{p.id}] analyzed with {memo.analyzer}: {n_claims} source-supported claims, "
          f"{len(memo.warnings)} warnings — {p.title[:70]}")
    if out_dir:
        export_obsidian([(p, memo)], out_dir)
    return 0


def cmd_analyze(args) -> int:
    if args.analyzer == "claude":
        print("NOTE: the Claude analyzer calls the Anthropic API. Usage is billed per token to the "
              "account owning ANTHROPIC_API_KEY, separately from Claude Code cloud-session credits.",
              file=sys.stderr)
        if not args.yes:
            print("Re-run with --yes to confirm.", file=sys.stderr)
            return 2
    analyzer = get_analyzer(args.analyzer, **({"model": args.model} if args.model else {}))
    with _store(args) as store:
        ids = args.id or [p.id for p in store.list(limit=args.top)]
        if args.text_file and len(ids) != 1:
            print("--text-file requires exactly one --id", file=sys.stderr)
            return 2
        rc = 0
        for pid in ids:
            try:
                rc |= _analyze_one(store, analyzer, pid, args.text_file, args.out)
            except Exception as exc:
                print(f"[{pid}] analysis failed: {exc}", file=sys.stderr)
                rc = 1
    return rc


def cmd_export(args) -> int:
    with _store(args) as store:
        papers = store.list(status=args.status, min_score=args.min_score)
        items = []
        for p in papers:
            a = store.latest_analysis(p.id)
            items.append((p, ResearchMemo.from_dict(a["memo_json"]) if a else None))
        paths = export_obsidian(items, args.vault, folder=args.folder)
    print(f"Wrote {len(paths)} files to {args.vault}")
    return 0


def cmd_demo(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db = out / "demo.db"
    if db.exists():
        db.unlink()
    print("Running OFFLINE demo with mocked OpenAlex / arXiv / Semantic Scholar responses.")
    print("The bundled demo papers are SYNTHETIC examples, not real publications.\n")
    with Store(db) as store:
        rep = discover(DEMO_QUERY, store=store, offline=True)
        print(f"Fetched: {rep.fetched}; after filters {rep.after_filter}; after dedup {rep.after_dedup}\n")
        _print_table(store.list())
        print()
        analyzer = get_analyzer("heuristic")
        for p in store.list(limit=args.top):
            _analyze_one(store, analyzer, p.id, None, None)
        items = []
        for p in store.list():
            a = store.latest_analysis(p.id)
            items.append((p, ResearchMemo.from_dict(a["memo_json"]) if a else None))
        paths = export_obsidian(items, out / "vault")
    print(f"\nDatabase: {db}\nObsidian vault: {out / 'vault'} ({len(paths)} files)")
    return 0


# ---- parser ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="paper-analyst", description=__doc__)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--db", help="SQLite path (default: $PAPER_ANALYST_DB or papers.db)")
    sub = ap.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="Search OpenAlex, arXiv and Semantic Scholar")
    d.add_argument("-k", "--keyword", action="append", help="Keyword/phrase (repeatable)")
    d.add_argument("-a", "--author", action="append", help="Researcher name (repeatable)")
    d.add_argument("-t", "--topic", action="append",
                   help=f"Topic preset or free text (repeatable). Presets: {', '.join(TOPIC_PRESETS)}")
    d.add_argument("--from", dest="date_from", help="Earliest publication date (YYYY[-MM[-DD]])")
    d.add_argument("--to", dest="date_to", help="Latest publication date (YYYY[-MM[-DD]])")
    d.add_argument("--source", action="append", choices=list(ALL_SOURCES), help="Restrict sources")
    d.add_argument("--limit", type=int, default=25, help="Max results per source")
    d.add_argument("--all", action="store_true", help="Require ALL keywords (default: any)")
    d.add_argument("--offline", action="store_true", help="Use bundled mocked API responses")
    d.set_defaults(func=cmd_discover)

    ls = sub.add_parser("list", help="List stored papers")
    ls.add_argument("--status", choices=[s.value for s in ResearchStatus])
    ls.add_argument("--min-score", type=float)
    ls.add_argument("--limit", type=int)
    ls.add_argument("--order", choices=["score", "date", "id"], default="score")
    ls.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="Show a paper (memo Markdown, or --json)")
    sh.add_argument("id", type=int)
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)

    r = sub.add_parser("rank", help="Recompute relevance scores for all stored papers")
    r.add_argument("--limit", type=int)
    r.set_defaults(func=cmd_rank)

    st = sub.add_parser("status", help="Show status counts, or set a paper's research status")
    st.add_argument("id", type=int, nargs="?")
    st.add_argument("set", nargs="?", choices=[s.value for s in ResearchStatus])
    st.add_argument("--notes", help="Attach free-text notes")
    st.set_defaults(func=cmd_status)

    an = sub.add_parser("analyze", help="Generate structured research memos")
    an.add_argument("--id", type=int, action="append", help="Paper id (repeatable); default: top-N")
    an.add_argument("--top", type=int, default=5, help="Analyze top-N ranked papers when no --id")
    an.add_argument("--analyzer", choices=["heuristic", "claude"], default="heuristic")
    an.add_argument("--model", help="Claude model id (default: $PAPER_ANALYST_CLAUDE_MODEL or claude-opus-5-5)")
    an.add_argument("--text-file", help="Plain-text full text of the paper to use as source")
    an.add_argument("--out", help="Also export memo(s) to this Obsidian vault directory")
    an.add_argument("--yes", action="store_true", help="Confirm paid Claude API usage")
    an.set_defaults(func=cmd_analyze)

    ex = sub.add_parser("export", help="Export notes + index to an Obsidian vault")
    ex.add_argument("--vault", required=True)
    ex.add_argument("--folder", default="Papers")
    ex.add_argument("--status", choices=[s.value for s in ResearchStatus])
    ex.add_argument("--min-score", type=float)
    ex.set_defaults(func=cmd_export)

    dm = sub.add_parser("demo", help="Run the full pipeline offline on mocked data")
    dm.add_argument("--out", default="demo_output")
    dm.add_argument("--top", type=int, default=5)
    dm.set_defaults(func=cmd_demo)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status" and args.id is not None and args.set is None:
        print("Usage: paper-analyst status <id> <new_status>", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
