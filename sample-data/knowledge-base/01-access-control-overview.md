# Access control overview

Every AegisAI request starts by authenticating a local user from an access JWT.
Authorization is a separate decision. The API loads the user and checks the
database-backed permissions granted through local roles.

`documents:read` permits document metadata, extraction, semantic retrieval, and
grounded chat. `documents:write` permits upload, rename, deletion, reprocessing,
and retrying failed work. Provider roles from Google, GitHub, and Microsoft
Entra are never copied into local authorization decisions.

The administrator role is a seeded system role with the current permission
catalogue. It is assigned locally after the first account exists. Future
document-level grants will narrow results even when two users both have the
global `documents:read` permission.
