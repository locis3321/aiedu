"""Celery worker 入口：`celery -A app.workers worker -l info`。"""

from app.jobs.tasks import celery_app

__all__ = ["celery_app"]
