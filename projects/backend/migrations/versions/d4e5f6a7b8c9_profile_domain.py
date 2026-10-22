"""profile domain schema (T12)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-10 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('profile_dimensions',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    # 首批维度集（教研资产，规格 v2 §10.1）
    op.bulk_insert(
        sa.table(
            'profile_dimensions',
            sa.column('code', sa.String),
            sa.column('name', sa.String),
            sa.column('version', sa.Integer),
            sa.column('active', sa.Boolean),
        ),
        [
            {'code': 'operations', 'name': '运算', 'version': 1, 'active': True},
            {'code': 'concept', 'name': '概念理解', 'version': 1, 'active': True},
            {'code': 'transfer', 'name': '应用迁移', 'version': 1, 'active': True},
            {'code': 'number_sense', 'name': '数感', 'version': 1, 'active': True},
        ],
    )
    op.create_table('profile_states',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('dimension_code', sa.String(length=32), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('evidence_count', sa.Integer(), nullable=False),
    sa.Column('needs_review_count', sa.Integer(), nullable=False),
    sa.Column('as_of_version', sa.Integer(), nullable=False),
    sa.Column('detail_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.ForeignKeyConstraint(['dimension_code'], ['profile_dimensions.code'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('child_id', 'dimension_code', name='uq_profile_child_dim')
    )
    op.create_index(op.f('ix_profile_states_child_id'), 'profile_states', ['child_id'], unique=False)
    op.create_table('profile_history',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('as_of_version', sa.Integer(), nullable=False),
    sa.Column('snapshot_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profile_history_child_id'), 'profile_history', ['child_id'], unique=False)
    op.create_table('trace_events',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('activity_id', sa.String(length=32), nullable=True),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trace_events_child_id'), 'trace_events', ['child_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_trace_events_child_id'), table_name='trace_events')
    op.drop_table('trace_events')
    op.drop_index(op.f('ix_profile_history_child_id'), table_name='profile_history')
    op.drop_table('profile_history')
    op.drop_index(op.f('ix_profile_states_child_id'), table_name='profile_states')
    op.drop_table('profile_states')
    op.drop_table('profile_dimensions')
