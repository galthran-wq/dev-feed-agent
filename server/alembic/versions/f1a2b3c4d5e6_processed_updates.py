"""processed_updates: dedup ledger for Telegram webhook update_ids

Revision ID: f1a2b3c4d5e6
Revises: b2c3d4e5f6a7

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'processed_updates',
        sa.Column('update_id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('update_id'),
    )


def downgrade() -> None:
    op.drop_table('processed_updates')
