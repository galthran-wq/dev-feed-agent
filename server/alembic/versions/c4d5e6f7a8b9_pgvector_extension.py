"""enable pgvector extension (for mem0 long-term memory)

mem0 creates and manages its own ``mem0_memories`` table at runtime; this migration only
ensures the ``vector`` extension it depends on is present. Requires a Postgres image that
ships pgvector (see docker-compose: pgvector/pgvector:pg15).

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
