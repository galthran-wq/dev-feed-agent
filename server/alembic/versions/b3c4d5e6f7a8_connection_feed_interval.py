"""per-user feed interval on connections

Adds connections.feed_interval_minutes (default daily) so feed cadence is per-user, not a
global hourly poll. server_default backfills existing rows to daily.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'connections',
        sa.Column('feed_interval_minutes', sa.Integer(), nullable=False, server_default='1440'),
    )


def downgrade() -> None:
    op.drop_column('connections', 'feed_interval_minutes')
