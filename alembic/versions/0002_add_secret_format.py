"""add secret_format to credentials

Revision ID: 0002_add_secret_format
Revises: 0001_initial
Create Date: 2026-03-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_secret_format"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("credentials", sa.Column("secret_format", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("credentials", "secret_format")
