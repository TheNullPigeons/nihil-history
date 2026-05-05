"""add engagement.nxc_workspace

Revision ID: 0006_add_engagement_nxc_workspace
Revises: 0005_hosts_nullable_ip
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_add_engagement_nxc_workspace"
down_revision = "0005_hosts_nullable_ip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("engagements") as batch_op:
        batch_op.add_column(sa.Column("nxc_workspace", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("engagements") as batch_op:
        batch_op.drop_column("nxc_workspace")
