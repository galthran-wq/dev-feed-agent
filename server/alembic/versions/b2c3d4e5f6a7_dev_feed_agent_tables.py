"""dev-feed-agent: github identity on users + connections, profiles, chat_messages, feed_items

Revision ID: b2c3d4e5f6a7
Revises: 64cd4beb4a5a

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = '64cd4beb4a5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- GitHub OAuth identity on users ---
    op.add_column('users', sa.Column('github_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('github_username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('github_access_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(), nullable=True))
    op.create_unique_constraint('uq_users_github_id', 'users', ['github_id'])

    op.create_table(
        'connections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('telegram_chat_id', sa.String(), nullable=True),
        sa.Column('telegram_link_code', sa.String(), nullable=False),
        sa.Column('feed_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_feed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('telegram_chat_id'),
        sa.UniqueConstraint('telegram_link_code'),
    )
    op.create_index(op.f('ix_connections_user_id'), 'connections', ['user_id'])

    op.create_table(
        'profiles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('sections', sa.JSON(), nullable=False),
        sa.Column('built_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index(op.f('ix_profiles_user_id'), 'profiles', ['user_id'])

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
        'feed_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('item_type', sa.String(length=32), nullable=False),
        sa.Column('external_id', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('bucket', sa.String(length=16), nullable=False, server_default=sa.text("'exploit'")),
        sa.Column('status', sa.String(length=16), nullable=False, server_default=sa.text("'delivered'")),
        sa.Column('delivered_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source', 'external_id', name='uq_feed_item_per_user'),
    )
    op.create_index(op.f('ix_feed_items_user_id'), 'feed_items', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_feed_items_user_id'), table_name='feed_items')
    op.drop_table('feed_items')
    op.drop_index(op.f('ix_chat_messages_user_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index(op.f('ix_profiles_user_id'), table_name='profiles')
    op.drop_table('profiles')
    op.drop_index(op.f('ix_connections_user_id'), table_name='connections')
    op.drop_table('connections')
    op.drop_constraint('uq_users_github_id', 'users', type_='unique')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'github_access_token')
    op.drop_column('users', 'github_username')
    op.drop_column('users', 'github_id')
