"""Safe errors raised by the derived Qdrant vector-store boundary."""


class VectorStoreError(RuntimeError):
    """Base error whose message is safe for a processing-job record."""


class VectorStoreConfigurationError(VectorStoreError):
    """The configured collection cannot safely store the active vectors."""


class VectorStoreOperationError(VectorStoreError):
    """Qdrant could not complete a collection or point operation."""
