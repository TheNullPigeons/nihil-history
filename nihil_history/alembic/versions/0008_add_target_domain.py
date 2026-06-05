"""add domain to targets

Revision ID: 0008_add_target_domain
Revises: 0007_add_targets
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_add_target_domain"
down_revision = "0007_add_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("domain", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("targets", "domain")
