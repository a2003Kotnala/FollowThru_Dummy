from __future__ import annotations

from celery import Celery
from celery.signals import task_postrun, worker_process_shutdown

from app.config import settings
from app.db.base import engine
from app.logger import logger

celery_app = Celery(
    "followthru",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)


@task_postrun.connect
def _dispose_sqlalchemy_connections(**_kwargs) -> None:
    try:
        engine.dispose()
    except Exception as exc:  # pragma: no cover - defensive cleanup
        logger.warning("Failed to dispose SQLAlchemy engine after Celery task: %s", exc)


@worker_process_shutdown.connect
def _dispose_sqlalchemy_connections_on_shutdown(**_kwargs) -> None:
    try:
        engine.dispose()
    except Exception as exc:  # pragma: no cover - defensive cleanup
        logger.warning(
            "Failed to dispose SQLAlchemy engine during Celery shutdown: %s",
            exc,
        )
