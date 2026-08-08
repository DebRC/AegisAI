"""Public, provider-neutral contract for Phase 10 semantic retrieval."""

from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator


RetrievalContentType = Literal[
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/markdown",
    "text/plain",
]

MAX_RETRIEVAL_QUERY_CHARACTERS = 10_000
MAX_RETRIEVAL_LIMIT = 20
MAX_RETRIEVAL_DOCUMENT_FILTERS = 100


class RetrievalSearchRequest(BaseModel):
    """A bounded semantic-search request without vendor-specific controls."""

    query: str = Field(min_length=1, max_length=MAX_RETRIEVAL_QUERY_CHARACTERS)
    limit: int = Field(default=10, ge=1, le=MAX_RETRIEVAL_LIMIT)
    document_ids: list[int] | None = Field(default=None, max_length=MAX_RETRIEVAL_DOCUMENT_FILTERS)
    content_types: list[RetrievalContentType] | None = Field(default=None, max_length=4)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(document_id < 1 for document_id in value) or len(set(value)) != len(value):
            raise ValueError("document_ids must contain unique positive integers")
        return value

    @field_validator("content_types")
    @classmethod
    def validate_content_types(
        cls,
        value: list[RetrievalContentType] | None,
    ) -> list[RetrievalContentType] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("content_types must not contain duplicates")
        return value


class RetrievalSearchResult(BaseModel):
    """One authoritative chunk result; score is Qdrant similarity, not a certainty."""

    document_id: int
    document_title: str
    content_type: RetrievalContentType
    chunk_id: int
    chunk_ordinal: int
    content: str
    source_locations: list[dict[str, int | str]] | None
    score: float = Field(allow_inf_nan=False)


class RetrievalSearchResponse(BaseModel):
    """Bounded ordered semantic-search results for the validated request."""

    items: list[RetrievalSearchResult] = Field(max_length=MAX_RETRIEVAL_LIMIT)
    limit: int = Field(ge=1, le=MAX_RETRIEVAL_LIMIT)
