"""add principal to targets

Revision ID: 0009_add_target_principal
Revises: 0008_add_target_domain
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_add_target_principal"
down_revision = "0008_add_target_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("principal", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("targets", "principal")
