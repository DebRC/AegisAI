# Stateless chat history boundaries

RAG chat accepts optional client-supplied history only as bounded context for
the next question. It allows at most ten complete prior messages, alternates
user and assistant roles, begins with a user message, and ends with an
assistant message. Developer and tool roles are rejected.

The history is marked untrusted in the prompt. It cannot override developer
instructions, change source labels, or serve as evidence for a factual claim.
Only the current PostgreSQL-verified retrieval results can support citations.

Phase 11 stores no conversation table or provider-hosted conversation ID. This
keeps the implementation stateless until retention and authorization rules for
shared conversations are deliberately designed.
