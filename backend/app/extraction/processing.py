"""Deterministic normalization and provenance-preserving text chunking."""

import re
import unicodedata
from dataclasses import dataclass

from app.extraction.base import ExtractedText
from app.extraction.base import SourceLocation
from app.extraction.exceptions import NoExtractableTextError


_DISALLOWED_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRAILING_HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+\n")
_EXCESSIVE_BLANK_LINES = re.compile(r"\n(?:[ ]*\n){2,}")
_SENTENCE_BOUNDARY = re.compile(r"[.!?](?=\s|$)")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedTextSpan:
    """A normalized-text range that came from one parser-provided location."""

    start_offset: int
    end_offset: int
    source_location: SourceLocation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.start_offset, int) or self.start_offset < 0:
            raise ValueError("normalized text span start_offset must be non-negative")
        if not isinstance(self.end_offset, int) or self.end_offset <= self.start_offset:
            raise ValueError("normalized text span end_offset must follow start_offset")


@dataclass(frozen=True)
class NormalizedText:
    """Clean text plus stable provenance spans used by the chunker."""

    text: str
    spans: tuple[NormalizedTextSpan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("normalized text must contain non-empty text")
        previous_end = 0
        for span in self.spans:
            if span.start_offset < previous_end or span.end_offset > len(self.text):
                raise ValueError("normalized text spans must be ordered and in bounds")
            previous_end = span.end_offset

    def source_locations_for_range(
        self,
        *,
        start_offset: int,
        end_offset: int,
    ) -> tuple[SourceLocation, ...]:
        """Return ordered unique parser locations overlapping a text range."""
        if not 0 <= start_offset < end_offset <= len(self.text):
            raise ValueError("text range must be non-empty and in bounds")
        locations: list[SourceLocation] = []
        for span in self.spans:
            if span.end_offset <= start_offset or span.start_offset >= end_offset:
                continue
            if span.source_location is not None and span.source_location not in locations:
                locations.append(span.source_location)
        return tuple(locations)


@dataclass(frozen=True)
class TextChunk:
    """One deterministic slice of normalized text, ready for persistence."""

    ordinal: int
    content: str
    start_offset: int
    end_offset: int
    source_locations: tuple[SourceLocation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise ValueError("chunk ordinal must be non-negative")
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("chunk content must be non-empty")
        if not isinstance(self.start_offset, int) or self.start_offset < 0:
            raise ValueError("chunk start_offset must be non-negative")
        if not isinstance(self.end_offset, int) or self.end_offset <= self.start_offset:
            raise ValueError("chunk end_offset must follow start_offset")
        if self.end_offset - self.start_offset != len(self.content):
            raise ValueError("chunk offsets must exactly match its content")


class TextNormalizer:
    """Normalize extractor blocks without losing their source provenance."""

    def normalize(self, extracted_text: ExtractedText) -> NormalizedText:
        parts: list[str] = []
        spans: list[NormalizedTextSpan] = []
        offset = 0
        for block in extracted_text.blocks:
            cleaned = self._clean_block(block.text)
            if not cleaned:
                continue
            if parts:
                parts.append("\n\n")
                offset += 2
            parts.append(cleaned)
            spans.append(
                NormalizedTextSpan(
                    start_offset=offset,
                    end_offset=offset + len(cleaned),
                    source_location=block.source_location,
                )
            )
            offset += len(cleaned)
        if not parts:
            raise NoExtractableTextError()
        return NormalizedText(text="".join(parts), spans=tuple(spans))

    @staticmethod
    def _clean_block(value: str) -> str:
        text = unicodedata.normalize("NFC", value)
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
        text = _DISALLOWED_CONTROL_CHARACTERS.sub("", text)
        text = _TRAILING_HORIZONTAL_WHITESPACE.sub("\n", text)
        text = _EXCESSIVE_BLANK_LINES.sub("\n\n", text)
        return text.strip()


class TextChunker:
    """Split normalized text at useful boundaries with bounded overlap."""

    def __init__(self, target_characters: int, overlap_characters: int):
        if (
            not isinstance(target_characters, int)
            or isinstance(target_characters, bool)
            or target_characters < 1
        ):
            raise ValueError("target_characters must be a positive integer")
        if (
            not isinstance(overlap_characters, int)
            or isinstance(overlap_characters, bool)
            or overlap_characters < 0
            or overlap_characters >= target_characters
        ):
            raise ValueError("overlap_characters must be non-negative and smaller than target_characters")
        self.target_characters = target_characters
        self.overlap_characters = overlap_characters

    def chunk(self, normalized_text: NormalizedText) -> list[TextChunk]:
        """Produce source-ordered chunks with exact normalized-text offsets."""
        text = normalized_text.text
        chunks: list[TextChunk] = []
        start_offset = self._skip_whitespace(text, 0)
        while start_offset < len(text):
            end_offset = self._choose_end_offset(text, start_offset)
            end_offset = self._trim_trailing_whitespace(text, start_offset, end_offset)
            if end_offset <= start_offset:
                end_offset = min(start_offset + self.target_characters, len(text))
            content = text[start_offset:end_offset]
            chunks.append(
                TextChunk(
                    ordinal=len(chunks),
                    content=content,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    source_locations=normalized_text.source_locations_for_range(
                        start_offset=start_offset,
                        end_offset=end_offset,
                    ),
                )
            )
            if end_offset == len(text):
                break
            start_offset = self._next_start_offset(text, start_offset, end_offset)
        return chunks

    def _choose_end_offset(self, text: str, start_offset: int) -> int:
        limit = min(start_offset + self.target_characters, len(text))
        if limit == len(text):
            return limit
        window = text[start_offset:limit]
        paragraph_boundary = window.rfind("\n\n")
        if paragraph_boundary >= 0:
            return start_offset + paragraph_boundary + 2
        sentence_boundaries = [match.end() for match in _SENTENCE_BOUNDARY.finditer(window)]
        if sentence_boundaries:
            return start_offset + sentence_boundaries[-1]
        whitespace_boundaries = [match.start() for match in _WHITESPACE.finditer(window)]
        if whitespace_boundaries:
            return start_offset + whitespace_boundaries[-1]
        return limit

    def _next_start_offset(self, text: str, start_offset: int, end_offset: int) -> int:
        if self.overlap_characters == 0:
            return self._skip_whitespace(text, end_offset)
        desired = max(start_offset + 1, end_offset - self.overlap_characters)
        boundary = desired
        while (
            boundary < end_offset
            and not text[boundary - 1].isspace()
            and not text[boundary].isspace()
        ):
            boundary += 1
        if boundary == end_offset:
            return desired
        return self._skip_whitespace(text, boundary)

    @staticmethod
    def _skip_whitespace(text: str, offset: int) -> int:
        while offset < len(text) and text[offset].isspace():
            offset += 1
        return offset

    @staticmethod
    def _trim_trailing_whitespace(text: str, start_offset: int, end_offset: int) -> int:
        while end_offset > start_offset and text[end_offset - 1].isspace():
            end_offset -= 1
        return end_offset
