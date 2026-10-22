"""llm credential column (LLM API Key 加密入库)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-13 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # LLM API Key（Fernet 密文，管理端可设；温度/超时/base_url 走 params_json）
    op.add_column('models_configs', sa.Column('api_key_enc', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('models_configs', 'api_key_enc')
