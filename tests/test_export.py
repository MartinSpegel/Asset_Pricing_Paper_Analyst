from paper_analyst.analysis import HeuristicAnalyzer
from paper_analyst.export import export_obsidian, note_name, render_memo, slugify
from paper_analyst.models import Paper


def test_slugify_removes_obsidian_illegal_chars():
    assert slugify('A: B/C [D] #E | "F"?') == "A B C D E F"


def test_render_memo_structure(sample_paper):
    sample_paper.relevance_score = 80.0
    sample_paper.relevance_breakdown = {"topics": {"Transfer learning": {"score": 90}}}
    md = render_memo(sample_paper, HeuristicAnalyzer().analyze(sample_paper))
    assert md.startswith("---\ntitle: ")
    assert "  - topic/transfer-learning" in md
    for h in ["## Research question", "## Economic mechanism", "## Methodology", "## Data",
              "## Results", "## Limitations", "## Research implications"]:
        assert h in md
    assert "**Source-supported claims**" in md
    assert "> [!note] Interpretation (not stated in source)" in md
    assert "_Not stated in the available source text._" in md  # e.g. economic mechanism
    assert "https://doi.org/10.5555/test.1" in md


def test_render_without_memo(sample_paper):
    md = render_memo(sample_paper, None)
    assert "## Abstract" in md and sample_paper.abstract in md


def test_export_obsidian(tmp_path, sample_paper):
    other = Paper(title="Pipes | and: colons", authors=[], relevance_score=1.0)
    paths = export_obsidian([(sample_paper, None), (other, None)], tmp_path)
    assert (tmp_path / "Paper Index.md") in paths
    index = (tmp_path / "Paper Index.md").read_text()
    assert f"[[Papers/{note_name(sample_paper)}\\|" in index
    assert (tmp_path / "Papers" / f"{note_name(other)}.md").exists()
    assert note_name(sample_paper).startswith("Lindqvist 2024 - ")
