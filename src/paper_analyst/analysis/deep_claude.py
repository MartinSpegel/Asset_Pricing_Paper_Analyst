"""Optional Claude-powered deep analyzer for full papers.

COST: every call is billed per token by Anthropic to the account owning
ANTHROPIC_API_KEY - separately from Claude Code cloud-session credits or any
Claude subscription. A full paper is typically tens of thousands of input
tokens. The CLI shows an estimate and requires ``--yes`` before calling.

Safety rails enforced in code, not only in the prompt:
* the model sees the paper as numbered blocks and must cite block ids; page and
  section locators are recomputed from the document, never taken from the model;
* author claims / evidence must be verbatim in the cited block or are dropped;
* interpretations without citations, and any interpretation or speculation
  containing numbers or author-year citations absent from the cited blocks,
  are dropped (see ``verify.validate_report``).
"""
from __future__ import annotations

import json
import os

from ..fulltext.model import Document
from ..profile import ResearchProfile, load_profile
from ..report import REPORT_SECTIONS, DeepReport, ItemKind, Locator, ReportItem
from ..verify import validate_report
from .deep_heuristic import init_report

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are a rigorous referee and research assistant in empirical asset pricing and \
machine learning in finance. You write a structured research report on ONE paper, using ONLY the \
paper text provided as numbered blocks.

Item kinds - keep them strictly separate:
- "author_claim": an exact, verbatim quote (a sentence or contiguous fragment of one block) in which \
the authors state a question, contribution, interpretation or conclusion. Cite exactly one block id.
- "evidence": an exact, verbatim quote of reported data, sample construction, variable definitions, \
design facts, estimates, statistics or table content. Cite exactly one block id.
- "interpretation": your own analytical reasoning (e.g. what the identification really relies on, \
weaknesses of the design, how results relate to SDF estimation or international asset pricing). \
Cite every block id you rely on. Give a short "basis".
- "speculation": research ideas that go beyond the paper. Label nothing else as speculation.

Hard rules:
1. Never paraphrase inside author_claim/evidence. Non-verbatim quotes are discarded automatically.
2. Never state a number in an interpretation or speculation unless it appears in a block you cite. \
Never invent quantitative findings, sample periods, datasets or test statistics.
3. Never cite literature, authors or papers that do not appear in the provided text.
4. If the paper does not address something, say so as an interpretation (e.g. "No discussion of \
transaction costs was found"), citing the closest relevant block if any.
5. In the critical assessment, separate what is identified from what is only "consistent with" the \
evidence; check out-of-sample design, look-ahead bias, multiple testing, inference, benchmarks, \
economic significance and implementability.
6. For research implications, distinguish genuine connections to the researcher's agenda from \
superficial keyword overlap."""


def _item_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": [k.value for k in ItemKind]},
            "text": {"type": "string"},
            "block_ids": {"type": "array", "items": {"type": "string"}},
            "basis": {"type": "string"},
        },
        "required": ["kind", "text", "block_ids", "basis"],
        "additionalProperties": False,
    }


REPORT_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "array", "items": _item_schema()} for k in REPORT_SECTIONS},
    "required": list(REPORT_SECTIONS),
    "additionalProperties": False,
}


def render_blocks(doc: Document) -> str:
    lines = []
    for b in doc.blocks:
        s = doc.section_of(b)
        page = f"p.{b.page}" + (f"-{b.page_end}" if b.page_end and b.page_end != b.page else "") if b.page else "p.?"
        lines.append(f"[{b.id} | {page} | {s.label if s else '-'} ({s.kind if s else '-'}) | {b.kind}]\n{b.text}")
    return "\n\n".join(lines)


def estimate_input_tokens(doc: Document) -> int:
    """Rough estimate (~4 characters per token) shown to the user before a paid call."""
    return (len(render_blocks(doc)) + len(SYSTEM_PROMPT) + 3000) // 4


class ClaudeDeepAnalyzer:
    name = "deep-claude"

    def __init__(self, client=None, model: str | None = None, profile: ResearchProfile | None = None,
                 effort: str = "high", use_fallbacks: bool = True, max_tokens: int = 32000):
        self.model = model or os.environ.get("PAPER_ANALYST_CLAUDE_MODEL") or DEFAULT_MODEL
        self.profile = profile or load_profile()
        self.effort, self.use_fallbacks, self.max_tokens = effort, use_fallbacks, max_tokens
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from .claude import ClaudeUnavailable
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise ClaudeUnavailable("Install the optional dependency: pip install -e '.[claude]'") from exc
            self._client = anthropic.Anthropic()
        return self._client

    def build_user_prompt(self, doc: Document, report: DeepReport) -> str:
        profile = {"name": self.profile.name, "description": self.profile.description,
                   "themes": [{"key": t.key, "name": t.name, "questions": t.questions} for t in self.profile.themes]}
        return ("RESEARCHER PROFILE:\n" + json.dumps(profile, indent=1) +
                "\n\nRULE-BASED CONNECTION ASSESSMENT (genuine = substantive work in core sections; superficial = "
                "keyword overlap only):\n" + json.dumps([{k: c[k] for k in ("key", "level", "rationale")}
                                                         for c in report.connections], indent=1) +
                "\n\nEXTRACTION WARNINGS:\n" + json.dumps(report.extraction_warnings) +
                "\n\nPAPER (numbered blocks; cite block ids such as b0012):\n<paper>\n" + render_blocks(doc) +
                "\n</paper>\n\nWrite the report. Sections: " + ", ".join(f"{k} = {v}" for k, v in REPORT_SECTIONS.items()))

    def _call(self, kwargs: dict):
        api = self.client.beta.messages if self.use_fallbacks else self.client.messages
        if self.use_fallbacks:
            kwargs = {**kwargs, "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        with api.stream(**kwargs) as stream:  # streaming: long input and output
            return stream.get_final_message()

    def analyze(self, doc: Document, paper_id: int | None = None, title: str | None = None) -> DeepReport:
        report, _ = init_report(doc, self.profile, self.name, self.model, paper_id, title)
        if not doc.blocks:
            report.validation_warnings.append("Document has no text; Claude was not called.")
            return report
        response = self._call(dict(
            model=self.model, max_tokens=self.max_tokens, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self.build_user_prompt(doc, report)}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": REPORT_SCHEMA}},
        ))
        stop = getattr(response, "stop_reason", None)
        if stop == "refusal":
            report.validation_warnings.append("Claude declined to analyze this paper (stop_reason=refusal).")
            return report
        if stop == "max_tokens":
            report.validation_warnings.append("Output truncated at max_tokens; report may be incomplete.")
        report.model = getattr(response, "model", None) or self.model
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            report.validation_warnings.append("Claude returned non-JSON output; no items recorded.")
            return report
        for key in REPORT_SECTIONS:
            for it in data.get(key, []) or []:
                if not isinstance(it, dict) or it.get("kind") not in {k.value for k in ItemKind}:
                    continue
                report.sections[key].append(ReportItem(
                    kind=it["kind"], text=str(it.get("text", "")).strip(), basis=str(it.get("basis", "")),
                    locators=[Locator(block_id=str(b)) for b in it.get("block_ids", [])], tags=["llm"]))
        return validate_report(report, doc)
