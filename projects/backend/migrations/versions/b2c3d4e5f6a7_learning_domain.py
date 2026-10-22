"""learning domain schema (T3)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-10 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('sessions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_child_id'), 'sessions', ['child_id'], unique=False)
    op.create_table('activities',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('lesson_id', sa.String(length=64), nullable=True),
    sa.Column('revision', sa.Integer(), nullable=True),
    sa.Column('spec_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('method_source', sa.String(length=8), nullable=True),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activities_session_id'), 'activities', ['session_id'], unique=False)
    op.create_index(op.f('ix_activities_child_id'), 'activities', ['child_id'], unique=False)
    op.create_table('attempts',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('activity_id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('step_id', sa.String(length=64), nullable=True),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('value_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('correct', sa.Boolean(), nullable=False),
    sa.Column('attempted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_attempts_activity_id'), 'attempts', ['activity_id'], unique=False)
    op.create_index(op.f('ix_attempts_child_id'), 'attempts', ['child_id'], unique=False)
    op.create_table('evidence',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('activity_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('detail_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id', 'kind', name='uq_activity_evidence_kind')
    )
    op.create_index(op.f('ix_evidence_child_id'), 'evidence', ['child_id'], unique=False)
    op.create_index(op.f('ix_evidence_session_id'), 'evidence', ['session_id'], unique=False)
    op.create_index(op.f('ix_evidence_activity_id'), 'evidence', ['activity_id'], unique=False)
    op.create_table('session_events',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('turn_id', sa.String(length=32), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('stage', sa.String(length=32), nullable=True),
    sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_session_events_session_id'), 'session_events', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_session_events_session_id'), table_name='session_events')
    op.drop_table('session_events')
    op.drop_index(op.f('ix_evidence_activity_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_session_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_child_id'), table_name='evidence')
    op.drop_table('evidence')
    op.drop_index(op.f('ix_attempts_child_id'), table_name='attempts')
    op.drop_index(op.f('ix_attempts_activity_id'), table_name='attempts')
    op.drop_table('attempts')
    op.drop_index(op.f('ix_activities_child_id'), table_name='activities')
    op.drop_index(op.f('ix_activities_session_id'), table_name='activities')
    op.drop_table('activities')
    op.drop_index(op.f('ix_sessions_child_id'), table_name='sessions')
    op.drop_table('sessions')
