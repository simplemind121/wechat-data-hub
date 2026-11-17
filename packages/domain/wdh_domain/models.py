from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Account(Base):
    __tablename__ = "wechat_accounts"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        UniqueConstraint("workspace_id", "account_ref"),
        UniqueConstraint("workspace_id", "id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    account_ref: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="unverified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Device(Base):
    __tablename__ = "source_devices"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        ForeignKeyConstraint(
            ["workspace_id", "account_id"], ["wechat_accounts.workspace_id", "wechat_accounts.id"]
        ),
        UniqueConstraint("workspace_id", "device_ref"),
        UniqueConstraint("workspace_id", "account_id", "id"),
        CheckConstraint("platform IN ('ios','macos','windows','other')"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    account_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    device_ref: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(20))
    os_version: Mapped[str | None] = mapped_column(String(100))
    wechat_version: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceBlob(Base):
    __tablename__ = "source_blobs"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        UniqueConstraint("workspace_id", "sha256"),
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("byte_size >= 0"),
        CheckConstraint("length(sha256) = 64"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    cas_key: Mapped[str] = mapped_column(String(200))
    storage_state: Mapped[str] = mapped_column(String(30), default="available")
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IngestBatch(Base):
    __tablename__ = "ingest_batches"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        ForeignKeyConstraint(
            ["workspace_id", "account_id"], ["wechat_accounts.workspace_id", "wechat_accounts.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "account_id", "device_id"],
            ["source_devices.workspace_id", "source_devices.account_id", "source_devices.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "main_blob_id"], ["source_blobs.workspace_id", "source_blobs.id"]
        ),
        UniqueConstraint("workspace_id", "main_blob_id", "adapter_id", "adapter_version"),
        UniqueConstraint("workspace_id", "id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    account_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    device_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    main_blob_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    adapter_id: Mapped[str] = mapped_column(String(100))
    adapter_version: Mapped[str] = mapped_column(String(30))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    original_timezone: Mapped[str | None] = mapped_column(String(100))
    batch_status: Mapped[str] = mapped_column(String(30), default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RawRecord(Base):
    __tablename__ = "raw_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "batch_id"], ["ingest_batches.workspace_id", "ingest_batches.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "raw_blob_id"], ["source_blobs.workspace_id", "source_blobs.id"]
        ),
        UniqueConstraint("batch_id", "source_record_locator"),
        CheckConstraint("length(raw_sha256) = 64"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    batch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    source_record_locator: Mapped[str] = mapped_column(String(1000))
    source_primary_key: Mapped[str | None] = mapped_column(String(200))
    raw_sha256: Mapped[str] = mapped_column(String(64))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    raw_blob_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    parse_status: Mapped[str] = mapped_column(String(30), default="pending")
    parse_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
