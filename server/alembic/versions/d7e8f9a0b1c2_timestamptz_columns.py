"""make all timestamp columns timezone-aware (timestamptz)

The app writes aware datetime.now(UTC) but the columns were created as
`timestamp without time zone`, which asyncpg rejects on Postgres. Convert them all to
`timestamp with time zone` (existing naive values are interpreted as UTC).

Revision ID: d7e8f9a0b1c2
Revises: e5b2c3d4f6a7

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'e5b2c3d4f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = [
    ("users", "created_at"),
    ("connections", "created_at"),
    ("connections", "updated_at"),
    ("connections", "last_feed_at"),
    ("profiles", "built_at"),
    ("profiles", "updated_at"),
    ("agent_messages", "created_at"),
    ("feed_items", "delivered_at"),
    ("processed_updates", "created_at"),
    ("memories", "created_at"),
    ("memories", "updated_at"),
]


def upgrade() -> None:
    for table, col in _COLUMNS:
        op.alter_column(
            table,
            col,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, col in _COLUMNS:
        op.alter_column(
            table,
            col,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )
