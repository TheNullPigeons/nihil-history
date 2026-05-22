"""add targets table

Revision ID: 0007_add_targets
Revises: 0006_add_engagement_nxc_workspace
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_add_targets"
down_revision = "0006_add_engagement_nxc_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("engagements.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("user", sa.String(length=255), nullable=True),
        sa.Column("group", sa.String(length=255), nullable=True),
        sa.Column("object", sa.String(length=255), nullable=True),
        sa.Column("computer", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_targets_engagement_id", "targets", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_targets_engagement_id", table_name="targets")
    op.drop_table("targets")
