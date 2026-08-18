# Embedding and vector indexing

When extraction is ready, an `embedding_indexing` job sends bounded chunk text
to the configured embedding provider. Vectors are validated for count,
dimension, and finite numeric values before they are stored in Qdrant.

PostgreSQL remains the authority for document, extraction, chunk, and embedding
identity. Qdrant stores derived search vectors and safe payload identifiers; it
does not decide whether a deleted or stale chunk may be returned.

Changing the embedding model or vector dimension requires a new Qdrant
collection and deliberate reprocessing. Do not mutate an existing collection
just to fit a changed configuration.
