"""Content-type dispatch and output limits for text extractors."""

from typing import BinaryIO

from app.extraction.base import ExtractedText, TextExtractor
from app.extraction.exceptions import ExtractedTextLimitExceededError
from app.extraction.exceptions import UnsupportedDocumentTypeError
from app.extraction.extractors import DocxTextExtractor, PdfTextExtractor, Utf8TextExtractor


class TextExtractorRegistry:
    """Resolve an allowlisted MIME type to an extractor with bounded output."""

    def __init__(
        self,
        maximum_characters: int,
        *,
        plain_text_extractor: TextExtractor | None = None,
        pdf_extractor: TextExtractor | None = None,
        docx_extractor: TextExtractor | None = None,
    ):
        if not isinstance(maximum_characters, int) or isinstance(maximum_characters, bool) or maximum_characters < 1:
            raise ValueError("maximum_characters must be a positive integer")
        text_extractor = plain_text_extractor or Utf8TextExtractor()
        self.maximum_characters = maximum_characters
        self.extractors: dict[str, TextExtractor] = {
            "text/plain": text_extractor,
            "text/markdown": text_extractor,
            "application/pdf": pdf_extractor or PdfTextExtractor(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": docx_extractor
            or DocxTextExtractor(),
        }

    def extract(self, *, content_type: str, source: BinaryIO) -> ExtractedText:
        """Extract one source and enforce the deployment's output budget."""
        extractor = self.extractors.get(self._normalized_content_type(content_type))
        if extractor is None:
            raise UnsupportedDocumentTypeError()
        result = extractor.extract(source)
        if len(result.text) > self.maximum_characters:
            raise ExtractedTextLimitExceededError()
        return result

    @staticmethod
    def _normalized_content_type(content_type: str) -> str:
        if not isinstance(content_type, str):
            return ""
        return content_type.split(";", maxsplit=1)[0].strip().lower()
