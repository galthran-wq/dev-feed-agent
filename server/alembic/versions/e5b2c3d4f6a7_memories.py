"""memories: a specific/local memory lane distinct from the profile

Revision ID: e5b2c3d4f6a7
Revises: b2c3d4e5f6a7

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5b2c3d4f6a7'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'memories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_memories_user_id'), 'memories', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_memories_user_id'), table_name='memories')
    op.drop_table('memories')
