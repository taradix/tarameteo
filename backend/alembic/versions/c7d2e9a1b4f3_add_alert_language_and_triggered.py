"""add alert language and triggered

Revision ID: c7d2e9a1b4f3
Revises: a41f56e76d2e
Create Date: 2026-11-10 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7d2e9a1b4f3'
down_revision: str | None = 'a41f56e76d2e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('alerts', sa.Column('language', sa.String(length=2), server_default='en', nullable=False))
    op.add_column('alerts', sa.Column('triggered', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('alerts') as batch_op:
        batch_op.drop_column('triggered')
        batch_op.drop_column('language')
