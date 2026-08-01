"""Format-neutral values returned by Phase 8 text extractors."""

from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class SourceLocation:
    """Optional human-readable origin of one text block within a source."""

    kind: str
    index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("source location kind must be a non-empty string")
        if self.index is not None and (not isinstance(self.index, int) or self.index < 1):
            raise ValueError("source location index must be a positive integer")


@dataclass(frozen=True)
class ExtractedTextBlock:
    """Text in source order, optionally tied to a page or paragraph."""

    text: str
    source_location: SourceLocation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("extracted text blocks must contain non-empty text")


@dataclass(frozen=True)
class ExtractedText:
    """Raw extractor output before Phase 8 cleaning and chunking."""

    blocks: tuple[ExtractedTextBlock, ...]

    def __post_init__(self) -> None:
        if not self.blocks:
            raise ValueError("extracted text must contain at least one block")

    @property
    def text(self) -> str:
        """Join blocks predictably while retaining their individual locations."""
        return "\n\n".join(block.text for block in self.blocks)


class TextExtractor(Protocol):
    """Extract text from a binary stream without storage or DB knowledge."""

    def extract(self, source: BinaryIO) -> ExtractedText:
        """Return source-ordered text or raise a safe domain exception."""
