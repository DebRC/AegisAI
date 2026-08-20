from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.models.document import DocumentStatus
from app.models.document_access_grant import DocumentAccessLevel
from app.models.processing_job import ProcessingJobStatus


class DocumentResponse(BaseModel):
    """Public metadata for a document; internal storage keys stay server-side."""

    id: int
    uploader_user_id: int
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    offset: int
    limit: int
    total: int


class DocumentRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(str_strip_whitespace=True)


class DocumentAccessGrantRequest(BaseModel):
    """The only mutable part of a direct document-access grant."""

    access_level: DocumentAccessLevel


class DocumentAccessGrantResponse(BaseModel):
    """A direct user grant; owner access remains implicit and is not listed."""

    document_id: int
    user_id: int
    access_level: DocumentAccessLevel
    granted_by_user_id: int

    model_config = ConfigDict(from_attributes=True)


class DocumentExtractionResponse(BaseModel):
    id: int
    document_id: int
    character_count: int
    extractor_version: str
    extracted_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkResponse(BaseModel):
    id: int
    ordinal: int
    content: str
    start_offset: int
    end_offset: int
    source_locations: list[dict[str, int | str]] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkListResponse(BaseModel):
    items: list[DocumentChunkResponse]
    offset: int
    limit: int
    total: int


class ProcessingJobResponse(BaseModel):
    id: int
    document_id: int
    job_type: str
    status: ProcessingJobStatus
    attempt_count: int
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessingJobListResponse(BaseModel):
    items: list[ProcessingJobResponse]


class DocumentEmbeddingStatusResponse(BaseModel):
    """Public progress for current derived vectors; internal index details stay private."""

    document_id: int
    total_chunks: int
    indexed_chunks: int
    indexing_status: Literal["not_started", "queued", "running", "succeeded", "failed", "cancelled"]
    indexing_attempt_count: int
    indexing_error: str | None
    cleanup_pending_count: int

    model_config = ConfigDict(from_attributes=True)
