"""Guard against accidentally committing API keys."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), re.compile(r"ANTHROPIC_API_KEY\s*=\s*['\"]?sk-"),
            re.compile(r"SEMANTIC_SCHOLAR_API_KEY\s*=\s*['\"]?[A-Za-z0-9]{20,}")]


def test_no_api_keys_in_repo():
    offenders = []
    for path in ROOT.rglob("*"):
        if any(part in {".git", ".venv", "venv", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        if path.is_file() and path.suffix in {".py", ".md", ".toml", ".json", ".xml", ".txt", ".example", ".cfg", ".yaml", ".yml"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(p.search(text) for p in PATTERNS):
                offenders.append(str(path))
    assert offenders == []
