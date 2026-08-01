"""Untrusted-document text extraction interfaces and adapters."""

from app.extraction.base import ExtractedText
from app.extraction.base import ExtractedTextBlock
from app.extraction.base import SourceLocation
from app.extraction.exceptions import EncryptedDocumentError
from app.extraction.exceptions import ExtractedTextLimitExceededError
from app.extraction.exceptions import NoExtractableTextError
from app.extraction.exceptions import TextDecodingError
from app.extraction.exceptions import TextExtractionError
from app.extraction.exceptions import TextExtractionProviderError
from app.extraction.exceptions import UnsupportedDocumentTypeError
from app.extraction.base import TextExtractor
from app.extraction.registry import TextExtractorRegistry

__all__ = [
    "EncryptedDocumentError",
    "ExtractedText",
    "ExtractedTextBlock",
    "ExtractedTextLimitExceededError",
    "NoExtractableTextError",
    "SourceLocation",
    "TextDecodingError",
    "TextExtractionError",
    "TextExtractionProviderError",
    "TextExtractor",
    "TextExtractorRegistry",
    "UnsupportedDocumentTypeError",
]
