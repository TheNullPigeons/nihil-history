"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engagements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_engagement_name"),
    )
    op.create_table(
        "credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("engagements.id"), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("secret", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("cred_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_credentials_engagement_id", "credentials", ["engagement_id"])
    op.create_table(
        "hosts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("engagements.id"), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("operating_system", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hosts_engagement_id", "hosts", ["engagement_id"])
    op.create_table(
        "access_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("engagements.id"), nullable=False),
        sa.Column("cred_id", sa.Integer(), sa.ForeignKey("credentials.id"), nullable=False),
        sa.Column("host_id", sa.Integer(), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_access_links_engagement_id", "access_links", ["engagement_id"])
    op.create_index("ix_access_links_cred_id", "access_links", ["cred_id"])
    op.create_index("ix_access_links_host_id", "access_links", ["host_id"])


def downgrade() -> None:
    op.drop_index("ix_access_links_host_id", table_name="access_links")
    op.drop_index("ix_access_links_cred_id", table_name="access_links")
    op.drop_index("ix_access_links_engagement_id", table_name="access_links")
    op.drop_table("access_links")
    op.drop_index("ix_hosts_engagement_id", table_name="hosts")
    op.drop_table("hosts")
    op.drop_index("ix_credentials_engagement_id", table_name="credentials")
    op.drop_table("credentials")
    op.drop_table("engagements")
