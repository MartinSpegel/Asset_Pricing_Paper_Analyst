import pytest

from paper_analyst.cli import main


def test_demo_end_to_end(tmp_path, capsys):
    assert main(["demo", "--out", str(tmp_path), "--top", "3"]) == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out and "after dedup 5" in out
    notes = list((tmp_path / "vault" / "Papers").glob("*.md"))
    assert len(notes) == 5
    assert (tmp_path / "vault" / "Paper Index.md").exists()
    analyzed = [n for n in notes if "analyzer: heuristic" in n.read_text()]
    assert len(analyzed) == 3


def test_discover_list_status_analyze_export(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    assert main(["--db", db, "discover", "--offline", "-t", "sdf", "-t", "transfer_learning",
                 "--from", "2020"]) == 0
    out = capsys.readouterr().out
    assert "OFFLINE" in out and "Transfer Learning Across Equity Markets" in out
    assert main(["--db", db, "discover", "--offline", "-a", "Ada Lindqvist", "-k", "stochastic discount factor"]) == 0
    out = capsys.readouterr().out
    assert "new in DB: 0" in out  # everything merged into existing rows
    assert main(["--db", db, "status", "1", "reading", "--notes", "key paper"]) == 0
    assert main(["--db", db, "list", "--status", "reading"]) == 0
    assert "Transfer Learning" in capsys.readouterr().out
    assert main(["--db", db, "rank"]) == 0
    assert main(["--db", db, "analyze", "--id", "1", "--out", str(tmp_path / "v")]) == 0
    assert main(["--db", db, "show", "1"]) == 0
    shown = capsys.readouterr().out
    assert "## Results" in shown and "key paper" in shown
    assert main(["--db", db, "export", "--vault", str(tmp_path / "vault2")]) == 0
    assert (tmp_path / "vault2" / "Paper Index.md").exists()


def test_discover_requires_criteria(tmp_path):
    assert main(["--db", str(tmp_path / "t.db"), "discover", "--offline"]) == 2


def test_claude_requires_confirmation(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "t.db"), "analyze", "--analyzer", "claude"]) == 2
    assert "billed" in capsys.readouterr().err


def test_bad_status(tmp_path):
    with pytest.raises(SystemExit):
        main(["--db", str(tmp_path / "t.db"), "status", "1", "nonsense"])
