"""accounts domain schema (T2)

Revision ID: a1b2c3d4e5f6
Revises: 9834b4b1753a
Create Date: 2026-10-10 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9834b4b1753a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('wechat_openid', sa.String(length=64), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('nickname', sa.String(length=64), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('wechat_openid'),
    sa.UniqueConstraint('phone')
    )
    op.create_table('children',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('parent_id', sa.String(length=32), nullable=False),
    sa.Column('nickname', sa.String(length=32), nullable=False),
    sa.Column('grade', sa.String(length=16), nullable=True),
    sa.Column('age_group', sa.String(length=16), nullable=True),
    sa.Column('textbook_version', sa.String(length=32), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_children_parent_id'), 'children', ['parent_id'], unique=False)
    op.create_table('consents',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('parent_id', sa.String(length=32), nullable=False),
    sa.Column('consent_key', sa.String(length=48), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('parent_id', 'consent_key', name='uq_parent_consent')
    )
    op.create_index(op.f('ix_consents_parent_id'), 'consents', ['parent_id'], unique=False)
    op.create_table('sms_verifications',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('mode', sa.String(length=8), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sms_verifications_phone'), 'sms_verifications', ['phone'], unique=False)
    op.create_table('usage_settings',
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('daily_minutes', sa.Integer(), nullable=False),
    sa.Column('continuous_minutes', sa.Integer(), nullable=False),
    sa.Column('rest_minutes', sa.Integer(), nullable=False),
    sa.Column('companion_enabled', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('child_id')
    )


def downgrade() -> None:
    op.drop_table('usage_settings')
    op.drop_index(op.f('ix_sms_verifications_phone'), table_name='sms_verifications')
    op.drop_table('sms_verifications')
    op.drop_index(op.f('ix_consents_parent_id'), table_name='consents')
    op.drop_table('consents')
    op.drop_index(op.f('ix_children_parent_id'), table_name='children')
    op.drop_table('children')
    op.drop_table('users')
