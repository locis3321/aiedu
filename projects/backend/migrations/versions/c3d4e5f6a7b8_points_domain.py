"""points domain schema (T4)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('reward_rules',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=24), nullable=False),
    sa.Column('points_independent', sa.Integer(), nullable=False),
    sa.Column('points_assisted', sa.Integer(), nullable=False),
    sa.Column('points_demonstrated', sa.Integer(), nullable=False),
    sa.Column('daily_cap', sa.Integer(), nullable=True),
    sa.Column('per_event_cap', sa.Integer(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ledger',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('evidence_id', sa.String(length=32), nullable=True),
    sa.Column('event_type', sa.String(length=24), nullable=False),
    sa.Column('rule_version', sa.Integer(), nullable=True),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('balance_after', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('evidence_id', 'event_type', name='uq_ledger_evidence_event')
    )
    op.create_index(op.f('ix_ledger_child_id'), 'ledger', ['child_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ledger_child_id'), table_name='ledger')
    op.drop_table('ledger')
    op.drop_table('reward_rules')
