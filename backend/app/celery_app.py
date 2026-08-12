from celery import Celery

from app.config import settings

celery_app = Celery(
    "repotraverse_worker",
    broker=settings.celery_redis_url,
    backend=settings.celery_redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,
    beat_schedule={
        "cleanup-expired-repositories": {
            "task": "app.tasks.cleanup_repositories",
            "schedule": float(settings.repo_cleanup_interval_seconds),
        },
    },
)

celery_app.autodiscover_tasks(["app"])
