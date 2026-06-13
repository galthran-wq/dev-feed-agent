"""rate-limit: add connections.last_profile_build_at (for the /rebuild cooldown)

Revision ID: d4a1b2c3e5f6
Revises: b2c3d4e5f6a7

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a1b2c3e5f6'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('connections', sa.Column('last_profile_build_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('connections', 'last_profile_build_at')
