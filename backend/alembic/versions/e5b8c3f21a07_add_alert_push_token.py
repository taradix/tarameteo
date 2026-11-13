"""add alert push token

Revision ID: e5b8c3f21a07
Revises: c7d2e9a1b4f3
Create Date: 2026-11-13 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b8c3f21a07'
down_revision: str | None = 'c7d2e9a1b4f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A push alert has a token instead of an address; SQLite can't drop NOT NULL in place, so batch mode recreates the table.
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.alter_column('email', existing_type=sa.String(length=255), nullable=True)
    op.add_column('alerts', sa.Column('push_token', sa.String(length=512), nullable=True))
    op.create_index('idx_alerts_push_token', 'alerts', ['push_token'])


def downgrade() -> None:
    op.execute('DELETE FROM alerts WHERE push_token IS NOT NULL')
    op.drop_index('idx_alerts_push_token', table_name='alerts')
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.drop_column('push_token')
        batch_op.alter_column('email', existing_type=sa.String(length=255), nullable=False)
