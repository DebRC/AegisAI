"""Safe domain errors for untrusted-document text extraction."""


class TextExtractionError(Exception):
    """Base error for a source that cannot produce safe usable text."""


class UnsupportedDocumentTypeError(TextExtractionError):
    """Raised when no registered extractor supports a document MIME type."""


class TextDecodingError(TextExtractionError):
    """Raised when a text source is not valid UTF-8."""


class EncryptedDocumentError(TextExtractionError):
    """Raised when extraction would require handling protected content."""


class NoExtractableTextError(TextExtractionError):
    """Raised when a valid source contains no usable text."""


class ExtractedTextLimitExceededError(TextExtractionError):
    """Raised when parser output exceeds the configured character limit."""


class TextExtractionProviderError(TextExtractionError):
    """Raised when a parser cannot safely read an otherwise supported source."""
