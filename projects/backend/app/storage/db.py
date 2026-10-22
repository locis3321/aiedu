"""SQLAlchemy engine/session（psycopg3），配置从环境变量读取。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def create_db_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # 连接快速失败：DB 不可达时数秒内显式失败/回退，而不是长时间挂起
        # （runtime_config 兜底、worker 任务都需要这个上限）
        kwargs["connect_args"] = {"connect_timeout": 3}
    return create_engine(settings.database_url, **kwargs)


def create_session_factory():
    return sessionmaker(bind=create_db_engine(), expire_on_commit=False)
