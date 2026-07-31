from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict

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
