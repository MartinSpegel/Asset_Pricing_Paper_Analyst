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


def get_deep_analyzer(name: str, **kwargs):
    if name == "heuristic":
        from .deep_heuristic import DeepHeuristicAnalyzer
        return DeepHeuristicAnalyzer(profile=kwargs.get("profile"))
    if name == "claude":
        from .deep_claude import ClaudeDeepAnalyzer
        return ClaudeDeepAnalyzer(**kwargs)
    raise ValueError(f"Unknown deep analyzer: {name}")
