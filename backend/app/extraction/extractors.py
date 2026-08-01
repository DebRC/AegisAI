"""Pure extraction adapters for the Phase 8 supported source formats."""

from collections.abc import Callable
from typing import Any, BinaryIO

from app.extraction.base import ExtractedText, ExtractedTextBlock, SourceLocation
from app.extraction.exceptions import EncryptedDocumentError
from app.extraction.exceptions import NoExtractableTextError
from app.extraction.exceptions import TextDecodingError
from app.extraction.exceptions import TextExtractionProviderError


class Utf8TextExtractor:
    """Decode plain-text and Markdown sources without guessing an encoding."""

    def extract(self, source: BinaryIO) -> ExtractedText:
        data = source.read()
        if not isinstance(data, bytes):
            raise TextExtractionProviderError()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise TextDecodingError() from error
        return _result_from_blocks(
            [ExtractedTextBlock(text=text, source_location=SourceLocation("document"))]
            if text.strip()
            else []
        )


class PdfTextExtractor:
    """Extract selectable text from PDF pages without OCR or decryption."""

    def __init__(self, reader_factory: Callable[[BinaryIO], Any] | None = None):
        self.reader_factory = reader_factory or self._load_reader

    def extract(self, source: BinaryIO) -> ExtractedText:
        try:
            reader = self.reader_factory(source)
            if reader.is_encrypted:
                raise EncryptedDocumentError()
            blocks = [
                ExtractedTextBlock(
                    text=text,
                    source_location=SourceLocation("page", index=page_number),
                )
                for page_number, page in enumerate(reader.pages, start=1)
                if isinstance((text := page.extract_text()), str) and text.strip()
            ]
        except EncryptedDocumentError:
            raise
        except Exception as error:
            raise TextExtractionProviderError() from error
        return _result_from_blocks(blocks)

    @staticmethod
    def _load_reader(source: BinaryIO) -> Any:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise TextExtractionProviderError() from error
        return PdfReader(source, strict=False)


class DocxTextExtractor:
    """Extract readable DOCX paragraphs without rendering or macro execution."""

    def __init__(self, document_factory: Callable[[BinaryIO], Any] | None = None):
        self.document_factory = document_factory or self._load_document

    def extract(self, source: BinaryIO) -> ExtractedText:
        try:
            document = self.document_factory(source)
            blocks = [
                ExtractedTextBlock(
                    text=text,
                    source_location=SourceLocation("paragraph", index=paragraph_number),
                )
                for paragraph_number, paragraph in enumerate(document.paragraphs, start=1)
                if isinstance((text := paragraph.text), str) and text.strip()
            ]
        except Exception as error:
            raise TextExtractionProviderError() from error
        return _result_from_blocks(blocks)

    @staticmethod
    def _load_document(source: BinaryIO) -> Any:
        try:
            from docx import Document as DocxDocument
        except ImportError as error:
            raise TextExtractionProviderError() from error
        return DocxDocument(source)


def _result_from_blocks(blocks: list[ExtractedTextBlock]) -> ExtractedText:
    """Map empty parser output to one consistent, safe domain exception."""
    if not blocks:
        raise NoExtractableTextError()
    return ExtractedText(blocks=tuple(blocks))
