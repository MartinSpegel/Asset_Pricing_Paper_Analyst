import json
import sqlite3
from pathlib import Path

from paper_analyst.cli import main

DEMO = str(Path(__file__).resolve().parents[1] / "sample_data" / "demo_paper.pdf")


def test_extract_command(tmp_path, capsys):
    assert main(["extract", DEMO, "--json", str(tmp_path / "d.json"), "--markdown", str(tmp_path / "d.md")]) == 0
    out = capsys.readouterr().out
    assert "§6 Empirical Results" in out and "two_column" in out
    assert json.loads((tmp_path / "d.json").read_text())["num_pages"] == 2
    assert "<!-- b0016 p.1" in (tmp_path / "d.md").read_text()


def test_ingest_deep_analyze_audit(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    assert main(["--db", db, "ingest", DEMO]) == 0
    assert "Ingested into paper [1]" in capsys.readouterr().out
    assert main(["--db", db, "deep-analyze", "--id", "1", "--out", str(tmp_path / "vault")]) == 0
    out = capsys.readouterr().out
    assert "superficial" in out and "dropped 0" in out
    notes = list((tmp_path / "vault" / "Reports").glob("*.md"))
    assert len(notes) == 1 and "## 10. Open research questions" in notes[0].read_text()
    assert main(["--db", db, "audit", "--id", "1"]) == 0
    assert main(["--db", db, "audit", "--id", "1", "--source", DEMO]) == 0
    # Tamper with the stored report: the audit must fail.
    con = sqlite3.connect(db)
    rj = json.loads(con.execute("SELECT report_json FROM reports").fetchone()[0])
    item = next(i for i in rj["sections"]["findings"] if i["kind"] == "evidence")
    item["text"] = item["text"].replace("14%", "41%")
    con.execute("UPDATE reports SET report_json = ?", (json.dumps(rj),))
    con.commit()
    con.close()
    capsys.readouterr()
    assert main(["--db", db, "audit", "--id", "1"]) == 1
    assert "AUDIT FAILED" in capsys.readouterr().out


def test_ingest_attaches_to_existing_paper_and_abstract_fallback(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    assert main(["--db", db, "discover", "--offline", "-t", "sdf"]) == 0
    assert main(["--db", db, "deep-analyze", "--id", "1"]) == 0
    err = capsys.readouterr().err
    assert "ABSTRACT ONLY" in err
    assert main(["--db", db, "ingest", DEMO, "--id", "1"]) == 0
    assert main(["--db", db, "ingest", DEMO, "--id", "999"]) == 1


def test_claude_needs_approval_and_shows_estimate(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    main(["--db", db, "ingest", DEMO])
    capsys.readouterr()
    assert main(["--db", db, "deep-analyze", "--id", "1", "--analyzer", "claude"]) == 2
    err = capsys.readouterr().err
    assert "input tokens" in err and "billed" in err and "--yes" in err


def test_extract_failure_exit_code(tmp_path, capsys):
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf")
    assert main(["extract", str(bad)]) == 1
    assert "Extraction failed" in capsys.readouterr().err


def test_profile_and_demo_fulltext(tmp_path, capsys):
    assert main(["profile"]) == 0
    assert "Stochastic discount factors" in capsys.readouterr().out
    assert main(["demo-fulltext", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out and "PASSED" in out
