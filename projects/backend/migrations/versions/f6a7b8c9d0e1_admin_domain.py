"""admin domain schema (T7)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-10 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 试卷模板/结果增加审核状态（A4/A15）
    op.add_column('exam_templates', sa.Column('review_status', sa.String(length=16), server_default='draft', nullable=False))
    op.add_column('exam_results', sa.Column('review_status', sa.String(length=16), server_default='unreviewed', nullable=False))

    op.create_table('reviews',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('revision_id', sa.String(length=32), nullable=False),
    sa.Column('lesson_id', sa.String(length=64), nullable=True),
    sa.Column('math_verified', sa.Boolean(), nullable=False),
    sa.Column('teaching_gate_ok', sa.Boolean(), nullable=False),
    sa.Column('age_ok', sa.Boolean(), nullable=False),
    sa.Column('layout_ok', sa.Boolean(), nullable=False),
    sa.Column('human_reviewed', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('reject_reason', sa.String(length=500), nullable=True),
    sa.Column('reviewed_by_role', sa.String(length=24), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('revision_id')
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('actor_role', sa.String(length=24), nullable=False),
    sa.Column('action', sa.String(length=48), nullable=False),
    sa.Column('target_type', sa.String(length=32), nullable=False),
    sa.Column('target_id', sa.String(length=64), nullable=True),
    sa.Column('detail_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('skills',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('referenced_count', sa.Integer(), nullable=False),
    sa.Column('manifest_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('prompts',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('models_configs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('credential_status', sa.String(length=16), nullable=False),
    sa.Column('params_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tts_configs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('voice', sa.String(length=64), nullable=True),
    sa.Column('rate', sa.Float(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ai_avatar_configs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('assets_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sms_templates',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('sign_name', sa.String(length=64), nullable=True),
    sa.Column('template_id', sa.String(length=64), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('safety_feedbacks',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=True),
    sa.Column('session_id', sa.String(length=32), nullable=True),
    sa.Column('summary_text', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('safety_feedbacks')
    op.drop_table('sms_templates')
    op.drop_table('ai_avatar_configs')
    op.drop_table('tts_configs')
    op.drop_table('models_configs')
    op.drop_table('prompts')
    op.drop_table('skills')
    op.drop_table('audit_logs')
    op.drop_table('reviews')
    op.drop_column('exam_results', 'review_status')
    op.drop_column('exam_templates', 'review_status')
