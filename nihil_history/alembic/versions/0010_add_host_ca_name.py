"""add CA name to hosts

Revision ID: 0010_add_host_ca_name
Revises: 0009_add_target_principal
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_host_ca_name"
down_revision = "0009_add_target_principal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("ca_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "ca_name")
