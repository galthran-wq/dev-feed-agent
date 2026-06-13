"""users

Revision ID: 64cd4beb4a5a
Revises: 

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '64cd4beb4a5a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('password_hash', sa.String(), nullable=True),
    sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )


def downgrade() -> None:
    op.drop_table('users')
