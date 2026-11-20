"""index lower alert email

Revision ID: f2a9d4c6b8e1
Revises: e5b8c3f21a07
Create Date: 2026-11-20 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2a9d4c6b8e1'
down_revision: str | None = 'e5b8c3f21a07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every lookup matches lower(email), which a plain index on email can't serve.
    op.drop_index('idx_alerts_email', table_name='alerts')
    op.create_index('idx_alerts_email', 'alerts', [sa.text('lower(email)')])


def downgrade() -> None:
    op.drop_index('idx_alerts_email', table_name='alerts')
    op.create_index('idx_alerts_email', 'alerts', ['email'])
