"""Shared Celery application used by the worker and scheduler processes."""

from celery import Celery
from celery.signals import task_postrun, task_failure

from app.core.logging import logger

from app.core.config import settings


def create_celery_app() -> Celery:
    """Build the constrained Celery runtime used for document processing."""

    application = Celery("aegis", include=["app.workers.tasks"])
    application.conf.update(
        broker_url=settings.CELERY_BROKER_URL,
        result_backend=settings.CELERY_RESULT_BACKEND,
        task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SECONDS,
        task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
        beat_schedule={
            "dispatch-processing-outbox": {
                "task": "app.workers.tasks.dispatch_processing_outbox",
                "schedule": settings.PROCESSING_OUTBOX_DISPATCH_INTERVAL_SECONDS,
            }
        },
    )
    return application


celery_app = create_celery_app()


@task_postrun.connect
def record_worker_success(sender=None, state=None, **_):
    if state == "SUCCESS":
        name = getattr(sender, "name", "unknown")
        logger.info(
            "worker_task_completed",
            extra={"task_name": name, "failure_category": "none"},
        )


@task_failure.connect
def record_worker_failure(sender=None, **_):
    name = getattr(sender, "name", "unknown")
    logger.warning(
        "worker_task_failed",
        extra={"task_name": name, "failure_category": "task_failure"},
    )
