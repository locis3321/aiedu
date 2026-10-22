"""outbox 派发器：轮询未派发记录 → Celery broker。

job创建与outbox写入在同一事务；worker以job_id+stage+input_hash幂等领取，
重复消息不重复发布。
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.storage.models import DispatchOutbox


def dispatch_pending(session: Session, celery_app, limit: int = 100) -> int:
    """把未派发的 outbox 记录投递到 Celery；返回派发条数。

    多 dispatcher 进程并发时不取同一批行（FOR UPDATE SKIP LOCKED；SQLite no-op）；
    先投递后标记（at-least-once），重复投递由 worker 幂等领取兜底，避免丢消息。
    """
    rows = (
        session.query(DispatchOutbox)
        .filter(DispatchOutbox.dispatched_at.is_(None))
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    for row in rows:
        celery_app.send_task("aiedu.generate_lesson", args=[row.job_id])
        row.dispatched_at = datetime.now()
        row.attempts += 1
    session.commit()
    return len(rows)


def run_forever(interval_seconds: float = 1.0) -> None:
    """派发器主循环：轮询 outbox → Celery；`python -m app.jobs.dispatcher`。"""
    import time

    from app.jobs.tasks import celery_app
    from app.storage.db import create_session_factory

    factory = create_session_factory()
    while True:
        with factory() as session:
            dispatched = dispatch_pending(session, celery_app)
            if dispatched:
                print(f"[dispatcher] dispatched {dispatched} job(s)")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_forever()
