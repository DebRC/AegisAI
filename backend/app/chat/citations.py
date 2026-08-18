"""Validate model source-label references against application-issued prompt sources."""

import re

from app.chat.prompting import GroundedPrompt
from app.schemas.chat import ChatCitation


_SOURCE_REFERENCE = re.compile(r"\[(S[^\]\s]*)\]")
_VALID_SOURCE_ID = re.compile(r"S[1-9][0-9]*")


class CitationValidationError(ValueError):
    """Raised when a model answer references an absent or malformed source ID."""


class CitationValidator:
    """Issue citation payloads only from the verified source registry in a prompt."""

    def citations_for(self, answer: str, prompt: GroundedPrompt) -> tuple[ChatCitation, ...]:
        """Return unique citations in first-reference order after strict validation."""
        if not isinstance(answer, str):
            raise CitationValidationError("Chat answer must be a string")

        known_sources = {source.source_id: source for source in prompt.sources}
        citations: list[ChatCitation] = []
        seen_source_ids: set[str] = set()
        for source_id in _SOURCE_REFERENCE.findall(answer):
            if not _VALID_SOURCE_ID.fullmatch(source_id) or source_id not in known_sources:
                raise CitationValidationError("Chat answer referenced an unknown source")
            if source_id in seen_source_ids:
                continue
            source = known_sources[source_id]
            citations.append(
                ChatCitation(
                    source_id=source.source_id,
                    document_id=source.document_id,
                    document_title=source.document_title,
                    content_type=source.content_type,
                    chunk_id=source.chunk_id,
                    chunk_ordinal=source.chunk_ordinal,
                    source_locations=(
                        [dict(location) for location in source.source_locations]
                        if source.source_locations is not None
                        else None
                    ),
                    score=source.score,
                )
            )
            seen_source_ids.add(source_id)
        return tuple(citations)
