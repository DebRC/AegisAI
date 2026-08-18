# AegisAI synthetic knowledge-base fixtures

These 30 files are fictional, safe-to-commit documents for exercising the full
local pipeline: upload, background validation, extraction, chunking, OpenAI
embeddings, Qdrant retrieval, streaming RAG chat, and later document-level
access control. They contain no real credentials, customer data, or production
policy.

The set intentionally overlaps. For example, search for `refresh token`,
`incident severity`, `document retention`, `SAML`, `outbox`, or `vector cleanup`
and compare retrieval and cited chat responses across several source documents.

Regenerate the PDF and DOCX fixtures when needed (the committed generator makes
their contents reviewable):

```bash
backend/venv/bin/python sample-data/generate_enterprise_fixtures.py
```

Upload all files after obtaining a `documents:write` token:

```bash
for document in sample-data/knowledge-base/*.{md,txt,pdf,docx}; do
  [ -f "$document" ] && [ "$(basename "$document")" != 'README.md' ] || continue
  case "$document" in
    *.md) upload_type='text/markdown' ;;
    *.txt) upload_type='text/plain' ;;
    *.pdf) upload_type='application/pdf' ;;
    *.docx) upload_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document' ;;
  esac
  curl --fail-with-body -X POST http://localhost:8000/documents \
    -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
    -F "file=@${document};type=${upload_type}"
done
```

Some `curl` installations label `.md` files as `application/octet-stream` by
default. The explicit `type=text/markdown` is therefore required; AegisAI
correctly rejects that generic binary MIME type.

Use `GET /documents/{id}/indexing-status` to wait for each document to reach
`succeeded`. Then use the same user (or another user with `documents:read`) to
test `/retrieval/search` and `/chat/stream`.

## Enterprise demo scenarios

After all files are indexed, use these questions to test overlapping retrieval
and grounded citations:

| Scenario | Query | Expected source themes |
| --- | --- | --- |
| Identity and access | `How are local roles reviewed and why are SSO claims insufficient?` | Access overview, SSO linking, quarterly access review, architecture review. |
| Incident response | `What is required in the first fifteen minutes of a Severity 1 incident?` | Incident severity, communications, incident-response playbook. |
| Secure data handling | `Which data must never appear in a knowledge-base document?` | Data classification, retention, privacy assessment. |
| Release engineering | `What should be verified before and after a schema change release?` | Change management, release readiness, onboarding. |
| Resilience | `How should derived vectors be restored after a disaster?` | Business continuity, disaster recovery, vector cleanup. |
| Grounded chat | `When should the assistant refuse to answer from model knowledge?` | RAG chat, customer support runbook, chat-history boundaries. |

Today, every user with `documents:read` can retrieve this shared demo data.
Phase 12 will use the same pack to demonstrate document grants, revocation, and
different search/chat results for different enterprise users.

The fixture set contains 10 Markdown records, 10 TXT records, 5 PDFs, and 5
DOCX files. The source generator uses fictional content only; no credentials,
real users, customer records, or production policies belong in this directory.
