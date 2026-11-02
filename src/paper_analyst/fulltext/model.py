"""Located document model.

A ``Document`` is an ordered list of ``Block``s (paragraphs, headings, footnotes,
table-like fragments). Every block records where it came from - physical page,
printed page label (if detected), column and bounding box - and which section
it belongs to. Downstream analysis may only quote text that exists in a block,
so every claim can be traced back to a page and section.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class ExtractionError(RuntimeError):
    """Raised when no trustworthy text can be extracted. Never papered over."""


class SectionKind(str, Enum):
    FRONT_MATTER = "front_matter"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    LITERATURE = "literature"
    THEORY = "theory"
    DATA = "data"
    METHODOLOGY = "methodology"
    RESULTS = "results"
    ROBUSTNESS = "robustness"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    APPENDIX = "appendix"
    OTHER = "other"


# Section kinds containing the paper's substantive work (used by the profile and checks).
CORE_KINDS = {SectionKind.THEORY, SectionKind.DATA, SectionKind.METHODOLOGY, SectionKind.RESULTS,
              SectionKind.ROBUSTNESS, SectionKind.APPENDIX}


@dataclass
class Block:
    id: str                      # stable id, e.g. "b0042"
    text: str
    kind: str = "paragraph"      # paragraph | heading | footnote | table | caption
    page: int | None = None      # 1-based physical page (None for plain text)
    printed_page: str | None = None  # page label printed on the page, if detected
    column: int = 0              # 0 = full width / single column, 1 = left, 2 = right
    bbox: tuple[float, float, float, float] | None = None
    section_id: str | None = None
    paragraph: int | None = None  # 1-based index among paragraphs within its section
    page_end: int | None = None   # last page the block runs onto (paragraphs may cross pages)
    page_offsets: list[list[int]] = field(default_factory=list)  # [[char_offset, page], ...]

    def pages_for_span(self, start: int, end: int) -> tuple[int | None, int | None]:
        """Physical pages covered by text[start:end] (handles paragraphs crossing pages)."""
        if not self.page_offsets:
            return self.page, self.page
        first = last = self.page_offsets[0][1]
        for off, pg in self.page_offsets:
            if off <= start:
                first = pg
            if off < end:
                last = pg
        return first, last


@dataclass
class Section:
    id: str                      # e.g. "s03"
    title: str
    number: str | None = None    # e.g. "4", "4.2", "A"
    level: int = 1
    kind: str = SectionKind.OTHER.value
    heading_block: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    block_ids: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"§{self.number} {self.title}" if self.number else self.title


@dataclass
class Document:
    source_path: str | None
    source_type: str             # "pdf" | "text" | "abstract"
    sha256: str | None = None
    title: str | None = None
    num_pages: int | None = None
    extractor: str = ""
    blocks: list[Block] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    page_layouts: dict[int, str] = field(default_factory=dict)   # page -> single|two_column|mixed|empty
    removed_lines: list[dict] = field(default_factory=list)       # headers/footers/page numbers dropped
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    # ---- lookup helpers --------------------------------------------------
    def block(self, block_id: str) -> Block | None:
        return self._block_index().get(block_id)

    def _block_index(self) -> dict[str, Block]:
        idx = getattr(self, "_bidx", None)
        if idx is None or len(idx) != len(self.blocks):
            idx = {b.id: b for b in self.blocks}
            object.__setattr__(self, "_bidx", idx)
        return idx

    def section(self, section_id: str | None) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)

    def section_of(self, block: Block) -> Section | None:
        return self.section(block.section_id)

    def blocks_of_kind(self, *kinds: str | SectionKind) -> list[Block]:
        wanted = {k.value if isinstance(k, SectionKind) else k for k in kinds}
        ids = {s.id for s in self.sections if s.kind in wanted}
        return [b for b in self.blocks if b.section_id in ids]

    def section_kinds_present(self) -> dict[str, list[int]]:
        """Map section kind -> sorted pages on which it appears."""
        out: dict[str, set[int]] = {}
        for s in self.sections:
            pages = (range(s.page_start, s.page_end + 1)
                     if s.page_start is not None and s.page_end is not None else [])
            out.setdefault(s.kind, set()).update(pages)
        return {k: sorted(v) for k, v in out.items()}

    def full_text(self, include_kinds: tuple[str, ...] = ("paragraph", "heading", "footnote", "table", "caption")) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.kind in include_kinds)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["page_layouts"] = {str(k): v for k, v in self.page_layouts.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        d = dict(d)
        d["blocks"] = [Block(**{**b, "bbox": tuple(b["bbox"]) if b.get("bbox") else None}) for b in d["blocks"]]
        d["sections"] = [Section(**s) for s in d["sections"]]
        d["page_layouts"] = {int(k): v for k, v in d.get("page_layouts", {}).items()}
        return cls(**d)

    def locator(self, block_id: str) -> dict:
        """Human/machine-readable provenance for a block."""
        b = self.block(block_id)
        if b is None:
            raise KeyError(block_id)
        s = self.section_of(b)
        return {
            "block_id": b.id, "page": b.page, "printed_page": b.printed_page,
            "section_id": s.id if s else None, "section": s.label if s else None,
            "section_kind": s.kind if s else None, "paragraph": b.paragraph, "block_kind": b.kind,
        }
