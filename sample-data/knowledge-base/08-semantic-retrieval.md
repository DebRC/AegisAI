# Semantic retrieval rules

Retrieval embeds one normalized query, searches the active Qdrant collection,
and applies only controlled metadata filters such as document IDs and MIME
types. Clients cannot pass arbitrary Qdrant filter payloads, collection names,
or vector data.

Search candidates from Qdrant are reloaded from PostgreSQL. The service
discards missing, deleted, stale, mismatched, or payload-inconsistent vectors.
Remaining results are deterministically ranked and returned with current chunk
text, source locations, document metadata, and similarity score.

At this stage `documents:read` is a global permission. Document-specific and
tenant-specific filtering is added after the access policy is designed.
