"""tts provider column (TTS 供应商管理端可切)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TTS 供应商（mimo/edge）管理端可切；默认 mimo
    op.add_column('tts_configs', sa.Column('provider', sa.String(length=16), server_default='mimo', nullable=False))


def downgrade() -> None:
    op.drop_column('tts_configs', 'provider')
