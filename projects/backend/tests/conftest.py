"""测试基础设施：单元档保持 hermetic（不直连真实 PG），e2e 标记的用例除外。

问题背景：runtime_config / llm_router 通过 create_session_factory() 直连
settings.database_url（真实 PG），单元测试的 SQLite 注入只覆盖 FastAPI 依赖。
该旁路在 PG 不可达时曾导致整套测试挂起（SYN 重试无上限）。
"""

import pytest

from app.storage import db as storage_db


def _fast_fail_factory():
    """绑定到空 SQLite 的 sessionmaker：任何查询快速失败（无表），
    使 runtime_config 走 env 回退、llm_router 走 env 回退，不触达真实 PG。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _hermetic_runtime_config(request, monkeypatch):
    """仅对非 e2e 用例生效：替换直连真库的工厂为快速失败工厂。"""
    if "e2e" in request.keywords:
        return
    monkeypatch.setattr(storage_db, "create_session_factory", _fast_fail_factory)
