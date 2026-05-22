from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Engagement(Base):
    __tablename__ = "engagements"
    __table_args__ = (UniqueConstraint("name", name="uq_engagement_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nxc_workspace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    credentials: Mapped[list["Credential"]] = relationship(back_populates="engagement", cascade="all,delete")
    hosts: Mapped[list["Host"]] = relationship(back_populates="engagement", cascade="all,delete")
    links: Mapped[list["AccessLink"]] = relationship(back_populates="engagement", cascade="all,delete")
    targets: Mapped[list["Target"]] = relationship(back_populates="engagement", cascade="all,delete")


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    engagement: Mapped["Engagement"] = relationship(back_populates="credentials")


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), nullable=False, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operating_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    engagement: Mapped["Engagement"] = relationship(back_populates="hosts")


class AccessLink(Base):
    __tablename__ = "access_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), nullable=False, index=True)
    cred_id: Mapped[int] = mapped_column(ForeignKey("credentials.id"), nullable=False, index=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id"), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    engagement: Mapped["Engagement"] = relationship(back_populates="links")
    credential: Mapped["Credential"] = relationship()
    host: Mapped["Host"] = relationship()


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object: Mapped[str | None] = mapped_column(String(255), nullable=True)
    computer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    engagement: Mapped["Engagement"] = relationship(back_populates="targets")
