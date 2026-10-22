"""Alembic 迁移环境：URL 从应用配置注入，不保存凭据。"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.accounts import models as accounts_models  # noqa: F401  账号域模型（T2）
from app.admin_api import models as admin_models  # noqa: F401  后台域模型（T7）
from app.core.config import get_settings
from app.learning import models as learning_models  # noqa: F401  学习域模型（T3）
from app.points import models as points_models  # noqa: F401  积分域模型（T4）
from app.profile import models as profile_models  # noqa: F401  画像域模型（T12）
from app.questionbank import models as questionbank_models  # noqa: F401  题库域模型（T5）
from app.storage import models  # noqa: F401  注册全部模型到 metadata
from app.storage.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
