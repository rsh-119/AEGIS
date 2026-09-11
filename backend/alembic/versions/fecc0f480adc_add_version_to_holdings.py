"""add version to holdings

Revision ID: fecc0f480adc
Revises: 35db4b3e54d8
Create Date: 2026-08-27 22:45:40.444617

Optimistic-concurrency-control column for Holding (models.py's
`version_id_col` mapper arg). server_default='1' (not just the ORM-level
Python default) so every existing row backfills to 1 instead of violating
NOT NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fecc0f480adc'
down_revision: Union[str, None] = '35db4b3e54d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('holdings', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('holdings', 'version')
