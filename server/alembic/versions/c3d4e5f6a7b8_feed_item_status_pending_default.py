"""feed_items.status defaults to 'pending' (delivery reconciliation)

Items are recorded "pending" at curation time and flipped to "delivered" only after a
successful Telegram send, so the shown-ledger and actual delivery stay reconciled.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'feed_items',
        'status',
        existing_type=sa.String(length=16),
        server_default=sa.text("'pending'"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'feed_items',
        'status',
        existing_type=sa.String(length=16),
        server_default=sa.text("'delivered'"),
        existing_nullable=False,
    )
