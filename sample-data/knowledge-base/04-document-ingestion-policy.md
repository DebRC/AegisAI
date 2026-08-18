# Document ingestion policy

Supported uploads are UTF-8 text, Markdown, PDF, and DOCX. The server streams
the file, validates its allowed content type and size, stores original bytes
outside PostgreSQL, and writes safe metadata in PostgreSQL. The client never
chooses the storage key or uploader ID.

Each document records an original filename, MIME type, byte size, SHA-256
checksum, generated storage key, uploader provenance, lifecycle status, and
timestamps. The default upload limit is 25 MiB.

Deleting a document hides it from normal reads and cancels outstanding work.
The physical-file cleanup is best effort so a storage failure does not restore
deleted metadata to readers.
