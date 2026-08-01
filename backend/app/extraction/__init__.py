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
from app.extraction.processing import NormalizedText
from app.extraction.processing import NormalizedTextSpan
from app.extraction.processing import TextChunk
from app.extraction.processing import TextChunker
from app.extraction.processing import TextNormalizer
from app.extraction.registry import TextExtractorRegistry

__all__ = [
    "EncryptedDocumentError",
    "ExtractedText",
    "ExtractedTextBlock",
    "ExtractedTextLimitExceededError",
    "NoExtractableTextError",
    "NormalizedText",
    "NormalizedTextSpan",
    "SourceLocation",
    "TextChunk",
    "TextChunker",
    "TextDecodingError",
    "TextExtractionError",
    "TextExtractionProviderError",
    "TextExtractor",
    "TextExtractorRegistry",
    "TextNormalizer",
    "UnsupportedDocumentTypeError",
]
