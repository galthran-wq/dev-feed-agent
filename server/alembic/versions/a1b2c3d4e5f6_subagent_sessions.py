"""subagent_sessions table

Resumable sub-agent conversations: one row per session, holding the full pydantic-ai trace,
owned per (user, kind). Mirrors agent_messages but session-keyed and overwritten in place.

Revision ID: a1b2c3d4e5f6
Revises: d7e8f9a0b1c2

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subagent_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_subagent_sessions_user_kind', 'subagent_sessions', ['user_id', 'kind'])


def downgrade() -> None:
    op.drop_index('ix_subagent_sessions_user_kind', table_name='subagent_sessions')
    op.drop_table('subagent_sessions')
