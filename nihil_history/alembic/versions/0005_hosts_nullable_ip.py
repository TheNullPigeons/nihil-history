"""make hosts.ip nullable

Revision ID: 0005_hosts_nullable_ip
Revises: 0004_add_host_role
Create Date: 2026-04-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_hosts_nullable_ip"
down_revision = "0004_add_host_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hosts") as batch_op:
        batch_op.alter_column("ip", existing_type=sa.String(64), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("hosts") as batch_op:
        batch_op.alter_column("ip", existing_type=sa.String(64), nullable=False)
