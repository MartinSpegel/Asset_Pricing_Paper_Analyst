"""Optional Claude-powered analyzer.

COST NOTE: Calls to the Claude API are billed per token by Anthropic to the
account that owns ANTHROPIC_API_KEY. This is separate from (and not covered
by) Claude Code cloud-session credits or a Claude.ai subscription. Nothing in
this project calls the API unless you explicitly pass ``--analyzer claude``.

Guarantees enforced in code (not just in the prompt):
* Every "claim" must be a verbatim quote from the supplied source text;
  non-verbatim quotes are dropped by ``validate_memo`` and logged as warnings.
* The schema has no field for citations/references, so the model cannot add
  external citations; interpretations are stored and rendered separately.
"""
from __future__ import annotations

import json
import os

from ..memo import SECTIONS, Interpretation, MemoSection, ResearchMemo, SourceClaim, validate_memo
from ..models import Paper

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are a careful research assistant for an academic working in empirical \
asset pricing and machine learning in finance. You write structured research memos about a \
single paper using ONLY the source text provided.

Rules:
1. "claims" must be exact, verbatim quotes copied from the source text (a full sentence or a \
contiguous fragment). Do not paraphrase inside a claim. Quotes that cannot be found verbatim are \
automatically discarded.
2. Never invent results, numbers, datasets, sample periods or citations. If the source text does \
not state something, leave "claims" empty for that section.
3. "interpretations" are your own analytical reading (e.g. the likely economic mechanism, how the \
method relates to SDF estimation or transfer learning, open questions). Each must state its basis. \
They will be shown to the reader explicitly labelled as AI interpretation.
4. Do not refer to other papers, authors or references that are not in the source text."""

_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {"type": "string"}},
        "interpretations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "basis": {"type": "string"}},
                "required": ["text", "basis"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims", "interpretations"],
    "additionalProperties": False,
}

MEMO_SCHEMA = {
    "type": "object",
    "properties": {k: _SECTION_SCHEMA for k in SECTIONS},
    "required": list(SECTIONS),
    "additionalProperties": False,
}


class ClaudeUnavailable(RuntimeError):
    pass


class ClaudeAnalyzer:
    name = "claude"

    def __init__(self, client=None, model: str | None = None, effort: str = "high",
                 use_fallbacks: bool = True):
        self.model = model or os.environ.get("PAPER_ANALYST_CLAUDE_MODEL") or DEFAULT_MODEL
        self.effort = effort
        self.use_fallbacks = use_fallbacks
        self._client = client

    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on env
                raise ClaudeUnavailable(
                    "The 'anthropic' package is not installed. Install with: pip install -e '.[claude]'") from exc
            try:
                self._client = anthropic.Anthropic()
            except Exception as exc:  # pragma: no cover - depends on env
                raise ClaudeUnavailable(f"Could not create Claude client (set ANTHROPIC_API_KEY): {exc}") from exc
        return self._client

    def build_user_prompt(self, paper: Paper, source: str, kind: str) -> str:
        meta = {
            "title": paper.title, "authors": paper.authors, "date": paper.publication_date,
            "venue": paper.venue, "doi": paper.doi, "arxiv_id": paper.arxiv_id,
        }
        return (f"Paper metadata (for context only, not a source of claims):\n{json.dumps(meta, indent=2)}\n\n"
                f"SOURCE TEXT ({kind.replace('_', ' ')}):\n<source>\n{source}\n</source>\n\n"
                "Produce the memo JSON with sections: " + ", ".join(SECTIONS) + ".")

    def analyze(self, paper: Paper, full_text: str | None = None) -> ResearchMemo:
        kind = "full_text" if full_text else "abstract"
        source = full_text or paper.abstract or ""
        memo = ResearchMemo(paper_id=paper.id, title=paper.title, analyzer=self.name,
                            model=self.model, source_text_kind=kind)
        if not source.strip():
            memo.warnings.append("No source text available; Claude was not called.")
            return memo

        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self.build_user_prompt(paper, source, kind)}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": MEMO_SCHEMA}},
        )
        if self.use_fallbacks:
            # If a safety classifier declines, the API re-runs the request on a
            # recommended fallback model instead of returning a refusal.
            response = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            response = self.client.messages.create(**kwargs)

        if getattr(response, "stop_reason", None) == "refusal":
            memo.warnings.append("Claude declined to analyze this paper (stop_reason=refusal).")
            return memo
        if getattr(response, "stop_reason", None) == "max_tokens":
            memo.warnings.append("Claude output was truncated (max_tokens); memo may be incomplete.")
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            memo.warnings.append("Claude returned non-JSON output; no claims recorded.")
            return memo
        memo.model = getattr(response, "model", None) or self.model
        for key in SECTIONS:
            sec = data.get(key) or {}
            memo.sections[key] = MemoSection(
                claims=[SourceClaim(text=c) for c in sec.get("claims", []) if isinstance(c, str) and c.strip()],
                interpretations=[Interpretation(text=i.get("text", ""), basis=i.get("basis", ""))
                                 for i in sec.get("interpretations", []) if i.get("text")],
            )
        return validate_memo(memo, source)
