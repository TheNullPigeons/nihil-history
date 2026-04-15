"""add role to hosts

Revision ID: 0004_add_host_role
Revises: 0003_credential_rework
Create Date: 2026-04-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_add_host_role"
down_revision = "0003_credential_rework"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("role", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "role")
