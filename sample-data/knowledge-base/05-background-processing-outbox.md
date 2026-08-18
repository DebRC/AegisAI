# Background processing and the outbox

Uploading a document creates a durable processing job and an outbox record in
the same database transaction. A dispatcher publishes the work to Redis and a
Celery worker performs long-running validation outside the HTTP request.

Processing jobs move through queued, running, succeeded, failed, or cancelled
states. The outbox makes broker publication recoverable: if Redis is briefly
unavailable, the durable event can be retried without losing the document job.

Duplicate task deliveries are expected. Workers claim jobs and perform
idempotent checks so the same document is not treated as two independent
successful processing runs.
