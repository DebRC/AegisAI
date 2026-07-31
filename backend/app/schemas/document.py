from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.models.document import DocumentStatus


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
