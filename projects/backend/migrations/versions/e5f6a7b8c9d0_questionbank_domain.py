"""questionbank domain schema (T5)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-10 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('questions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('knowledge_code', sa.String(length=64), nullable=False),
    sa.Column('grade', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('math_verified', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_questions_knowledge_code'), 'questions', ['knowledge_code'], unique=False)
    op.create_table('question_sources',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('endpoint', sa.String(length=255), nullable=True),
    sa.Column('quota', sa.String(length=64), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('knowledge_mapping_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('signature_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('exam_templates',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('question_ids_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('rules_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('exam_papers',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('template_id', sa.String(length=32), nullable=True),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('question_ids_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exam_papers_child_id'), 'exam_papers', ['child_id'], unique=False)
    op.create_table('exam_results',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('paper_id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('answers_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('evidence_levels_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['paper_id'], ['exam_papers.id'], ),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exam_results_child_id'), 'exam_results', ['child_id'], unique=False)
    op.create_table('practice_sets',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('child_id', sa.String(length=32), nullable=False),
    sa.Column('question_ids_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('basis_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_practice_sets_child_id'), 'practice_sets', ['child_id'], unique=False)
    op.create_table('knowledge_nodes',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('stage', sa.String(length=16), nullable=False),
    sa.Column('grade', sa.Integer(), nullable=False),
    sa.Column('unit_code', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    # 图谱种子：三学段示例节点（教研生产+后台审核维护）
    op.bulk_insert(
        sa.table(
            'knowledge_nodes',
            sa.column('code', sa.String),
            sa.column('title', sa.String),
            sa.column('stage', sa.String),
            sa.column('grade', sa.Integer),
            sa.column('unit_code', sa.String),
            sa.column('status', sa.String),
        ),
        [
            {'code': 'arithmetic.add_sub', 'title': '加减法运算（凑十法）', 'stage': 'primary', 'grade': 1, 'unit_code': 'u1-arithmetic-basic', 'status': 'open'},
            {'code': 'arithmetic.mul_div', 'title': '乘除法运算基础', 'stage': 'primary', 'grade': 3, 'unit_code': 'u2-mul-div-basic', 'status': 'open'},
            {'code': 'fraction.mean', 'title': '分数的意义（等分）', 'stage': 'primary', 'grade': 3, 'unit_code': 'u3-fraction-mean', 'status': 'open'},
            {'code': 'number.place_value', 'title': '数位与位值理解', 'stage': 'primary', 'grade': 2, 'unit_code': 'u4-place-value', 'status': 'open'},
            {'code': 'application.word_problem', 'title': '应用题与数量关系', 'stage': 'junior', 'grade': 7, 'unit_code': 'j1-word-problem', 'status': 'construction'},
            {'code': 'number.sense', 'title': '数感与估算策略', 'stage': 'senior', 'grade': 10, 'unit_code': 's1-number-sense', 'status': 'construction'},
        ],
    )


def downgrade() -> None:
    op.drop_table('knowledge_nodes')
    op.drop_index(op.f('ix_practice_sets_child_id'), table_name='practice_sets')
    op.drop_table('practice_sets')
    op.drop_index(op.f('ix_exam_results_child_id'), table_name='exam_results')
    op.drop_table('exam_results')
    op.drop_index(op.f('ix_exam_papers_child_id'), table_name='exam_papers')
    op.drop_table('exam_papers')
    op.drop_table('exam_templates')
    op.drop_table('question_sources')
    op.drop_index(op.f('ix_questions_knowledge_code'), table_name='questions')
    op.drop_table('questions')
