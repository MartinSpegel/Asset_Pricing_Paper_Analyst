"""Memo generators: an offline heuristic extractor and an optional Claude analyzer."""
from .heuristic import HeuristicAnalyzer

__all__ = ["HeuristicAnalyzer", "get_analyzer"]


def get_analyzer(name: str, **kwargs):
    if name == "heuristic":
        return HeuristicAnalyzer()
    if name == "claude":
        from .claude import ClaudeAnalyzer
        return ClaudeAnalyzer(**kwargs)
    raise ValueError(f"Unknown analyzer: {name}")
