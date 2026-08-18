# Grounded RAG chat

The chat endpoint retrieves current verified chunks before calling the model.
The prompt labels the sources as S1, S2, and so on. A grounded answer must refer
to at least one supplied source label. AegisAI validates labels itself and
creates citation metadata only from the verified retrieval results.

If retrieval returns no useful context, the system sends a fixed
insufficient-context answer and does not call the chat model. Provider errors,
raw prompts, credentials, vector point IDs, and exception details never appear
in the public stream.

Successful calls use Server-Sent Events: zero or more `answer_delta` events,
then `citations`, then `done`. The endpoint requires `documents:read`.
