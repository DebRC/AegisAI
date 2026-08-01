"""Storage boundary for original uploaded document bytes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4


class DocumentStorageError(Exception):
    """Raised when document bytes cannot be stored or removed safely."""


class StorageLimitExceededError(DocumentStorageError):
    """Raised when a streamed document exceeds the configured byte limit."""


class EmptyDocumentError(DocumentStorageError):
    """Raised when a streamed document contains no bytes."""


@dataclass(frozen=True)
class StoredDocument:
    """Metadata produced while an original document is streamed to storage."""

    storage_key: str
    size_bytes: int
    sha256: str


class DocumentStorage(ABC):
    """Store and remove original document bytes by opaque storage key."""

    @abstractmethod
    def store(self, chunks: Iterable[bytes]) -> StoredDocument:
        """Stream chunks to durable storage and return server-derived metadata."""

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Remove a stored original document. Missing objects are already removed."""

    @abstractmethod
    def iter_chunks(self, storage_key: str, chunk_size: int = 64 * 1024) -> Iterable[bytes]:
        """Stream an existing original document through the trusted storage key."""


class LocalDocumentStorage(DocumentStorage):
    """Persistent local-volume adapter for development and Docker deployments."""

    _STORAGE_KEY_PATTERN = re.compile(
        r"documents/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )

    def __init__(self, root_path: str | Path, maximum_bytes: int):
        if maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive")

        self.root_path = Path(root_path).resolve()
        self.maximum_bytes = maximum_bytes
        self._objects_path = self.root_path / "documents"
        self._objects_path.mkdir(parents=True, exist_ok=True)

    def store(self, chunks: Iterable[bytes]) -> StoredDocument:
        storage_key = self._new_storage_key()
        final_path = self._path_for_key(storage_key)
        temporary_path: Path | None = None
        size_bytes = 0
        digest = hashlib.sha256()

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".upload-",
                suffix=".tmp",
                dir=self._objects_path,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                for chunk in chunks:
                    data = self._validated_chunk(chunk)
                    size_bytes += len(data)
                    if size_bytes > self.maximum_bytes:
                        raise StorageLimitExceededError()
                    temporary_file.write(data)
                    digest.update(data)

            if size_bytes == 0:
                raise EmptyDocumentError()

            os.replace(temporary_path, final_path)
            temporary_path = None
            return StoredDocument(
                storage_key=storage_key,
                size_bytes=size_bytes,
                sha256=digest.hexdigest(),
            )
        except DocumentStorageError:
            self._remove_file(temporary_path)
            raise
        except Exception as error:
            self._remove_file(temporary_path)
            raise DocumentStorageError("Document storage operation failed") from error

    def delete(self, storage_key: str) -> None:
        path = self._path_for_key(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise DocumentStorageError("Document storage operation failed") from error

    def iter_chunks(self, storage_key: str, chunk_size: int = 64 * 1024) -> Iterable[bytes]:
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        path = self._path_for_key(storage_key)
        try:
            with path.open("rb") as source:
                while chunk := source.read(chunk_size):
                    yield chunk
        except OSError as error:
            raise DocumentStorageError("Document storage operation failed") from error

    def _new_storage_key(self) -> str:
        return f"documents/{uuid4()}"

    def _path_for_key(self, storage_key: str) -> Path:
        if not self._STORAGE_KEY_PATTERN.fullmatch(storage_key):
            raise ValueError("Invalid document storage key")

        path = (self.root_path / storage_key).resolve()
        if self.root_path not in path.parents:
            raise ValueError("Invalid document storage key")
        return path

    @staticmethod
    def _validated_chunk(chunk: bytes) -> bytes:
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise DocumentStorageError("Document content must be binary")
        return bytes(chunk)

    @staticmethod
    def _remove_file(path: Path | None) -> None:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
