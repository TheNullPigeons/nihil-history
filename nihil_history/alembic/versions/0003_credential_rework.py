"""credential rework: add password/hash, drop cred_type/secret_format, make username nullable

Revision ID: 0003_credential_rework
Revises: 0002_add_secret_format
Create Date: 2026-04-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_credential_rework"
down_revision = "0002_add_secret_format"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("credentials", sa.Column("password", sa.Text(), nullable=True))
    op.add_column("credentials", sa.Column("hash", sa.Text(), nullable=True))
    # Make username nullable
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.alter_column("username", existing_type=sa.String(255), nullable=True)
    op.drop_column("credentials", "cred_type")
    op.drop_column("credentials", "secret_format")


def downgrade() -> None:
    op.add_column("credentials", sa.Column("secret_format", sa.String(length=64), nullable=True))
    op.add_column("credentials", sa.Column("cred_type", sa.String(length=64), nullable=False, server_default="password"))
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.alter_column("username", existing_type=sa.String(255), nullable=False, server_default="")
    op.drop_column("credentials", "hash")
    op.drop_column("credentials", "password")
