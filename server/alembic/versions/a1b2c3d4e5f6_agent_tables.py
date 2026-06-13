"""agent tables: github profiles, interest profiles, chat messages, sent issues

Revision ID: a1b2c3d4e5f6
Revises: 64cd4beb4a5a

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '64cd4beb4a5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'github_profiles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('github_username', sa.String(), nullable=True),
        sa.Column('github_token', sa.String(), nullable=True),
        sa.Column('telegram_chat_id', sa.String(), nullable=True),
        sa.Column('telegram_link_code', sa.String(), nullable=False),
        sa.Column('poll_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_polled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('telegram_chat_id'),
        sa.UniqueConstraint('telegram_link_code'),
    )
    op.create_index(op.f('ix_github_profiles_user_id'), 'github_profiles', ['user_id'])

    op.create_table(
        'interest_profiles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('languages', sa.JSON(), nullable=False),
        sa.Column('topics', sa.JSON(), nullable=False),
        sa.Column('keywords', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index(op.f('ix_interest_profiles_user_id'), 'interest_profiles', ['user_id'])

    op.create_table(
        'chat_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_messages_user_id'), 'chat_messages', ['user_id'])

    op.create_table(
        'sent_issues',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('issue_id', sa.BigInteger(), nullable=False),
        sa.Column('repo_full_name', sa.String(), nullable=False),
        sa.Column('issue_url', sa.String(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('languages', sa.String(), nullable=True),
        sa.Column('stars', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('relevance', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'issue_id', name='uq_sent_issue_per_user'),
    )
    op.create_index(op.f('ix_sent_issues_user_id'), 'sent_issues', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_sent_issues_user_id'), table_name='sent_issues')
    op.drop_table('sent_issues')
    op.drop_index(op.f('ix_chat_messages_user_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index(op.f('ix_interest_profiles_user_id'), table_name='interest_profiles')
    op.drop_table('interest_profiles')
    op.drop_index(op.f('ix_github_profiles_user_id'), table_name='github_profiles')
    op.drop_table('github_profiles')
