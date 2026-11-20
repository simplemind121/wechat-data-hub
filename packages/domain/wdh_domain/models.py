from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
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
        UniqueConstraint("workspace_id", "id", name="uq_raw_workspace_id"),
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


def owned_constraints(*constraints: Any) -> tuple[Any, ...]:
    return (
        ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        UniqueConstraint("workspace_id", "id"),
        *constraints,
    )


class Owned(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SetupLock(Base):
    __tablename__ = "setup_locks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class Membership(Owned):
    __tablename__ = "memberships"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(["user_id"], ["users.id"]),
        UniqueConstraint("workspace_id", "user_id"),
        CheckConstraint("role IN ('admin','reviewer','reader')"),
    )
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    role: Mapped[str] = mapped_column(String(20))


class LoginSession(Owned):
    __tablename__ = "login_sessions"
    __table_args__ = owned_constraints(ForeignKeyConstraint(["user_id"], ["users.id"]))
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Job(Owned):
    __tablename__ = "jobs"
    __table_args__ = owned_constraints(UniqueConstraint("workspace_id", "kind", "idempotency_key"))
    kind: Mapped[str] = mapped_column(String(30))
    batch_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Contact(Owned):
    __tablename__ = "contacts"
    __table_args__ = owned_constraints(UniqueConstraint("workspace_id", "account_id", "native_ref"))
    account_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    native_ref: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(300))
    aliases: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    linked_contact_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))


class Conversation(Owned):
    __tablename__ = "conversations"
    __table_args__ = owned_constraints(UniqueConstraint("workspace_id", "account_id", "native_ref"))
    account_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    native_ref: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20), default="unknown")
    privacy_scope: Mapped[str] = mapped_column(String(30), default="private")


class Message(Owned):
    __tablename__ = "messages"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"], ["conversations.workspace_id", "conversations.id"]
        ),
        UniqueConstraint("workspace_id", "strong_key"),
    )
    account_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    conversation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    sender_contact_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    original_time_text: Mapped[str | None] = mapped_column(Text)
    original_time_precision: Mapped[str] = mapped_column(String(30), default="unknown")
    message_type: Mapped[str] = mapped_column(String(30), index=True)
    original_type_code: Mapped[str] = mapped_column(String(100))
    body_text: Mapped[str | None] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text, default="")
    direction: Mapped[str | None] = mapped_column(String(30))
    strong_key: Mapped[str | None] = mapped_column(String(64))
    weak_key: Mapped[str] = mapped_column(String(64), index=True)
    content_signature: Mapped[str] = mapped_column(String(64))
    native_server_id: Mapped[str | None] = mapped_column(String(200))
    normalization_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    merge_status: Mapped[str] = mapped_column(String(30), default="single_source")
    merged_into: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    reply_source_ref: Mapped[str | None] = mapped_column(String(200))
    reply_to_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))


class Observation(Owned):
    __tablename__ = "message_observations"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(
            ["workspace_id", "message_id"], ["messages.workspace_id", "messages.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "batch_id"], ["ingest_batches.workspace_id", "ingest_batches.id"]
        ),
        UniqueConstraint("raw_record_id"),
        ForeignKeyConstraint(
            ["workspace_id", "raw_record_id"],
            ["raw_records.workspace_id", "raw_records.id"],
            name="fk_obs_raw_workspace",
        ),
    )
    message_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    batch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    raw_record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    device_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    source_message_id: Mapped[str | None] = mapped_column(String(200))
    observed_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MessageEvent(Owned):
    __tablename__ = "message_events"
    __table_args__ = owned_constraints()
    message_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    raw_record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Attachment(Owned):
    __tablename__ = "attachments"
    __table_args__ = owned_constraints(UniqueConstraint("workspace_id", "sha256"))
    sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    original_filename: Mapped[str] = mapped_column(String(500))
    availability: Mapped[str] = mapped_column(String(30), default="missing")


class MessageAttachment(Owned):
    __tablename__ = "message_attachments"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(
            ["workspace_id", "message_id"], ["messages.workspace_id", "messages.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "attachment_id"], ["attachments.workspace_id", "attachments.id"]
        ),
        UniqueConstraint("raw_record_id", "position"),
    )
    message_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    attachment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    raw_record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    position: Mapped[int] = mapped_column(Integer)
    original_media_path: Mapped[str] = mapped_column(String(1000))


class Review(Owned):
    __tablename__ = "review_tasks"
    __table_args__ = owned_constraints(UniqueConstraint("workspace_id", "review_key"))
    review_key: Mapped[str] = mapped_column(String(200))
    review_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reviewer_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Owned):
    __tablename__ = "audit_events"
    __table_args__ = owned_constraints()
    actor_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    object_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(30), default="success")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class EntityAssertion(Owned):
    __tablename__ = "entity_assertions"
    __table_args__ = owned_constraints(UniqueConstraint("workspace_id", "extraction_key"))
    entity_type: Mapped[str] = mapped_column(String(30))
    extraction_key: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    approved_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    approved_by: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessingPolicy(Owned):
    __tablename__ = "processing_policies"
    __table_args__ = owned_constraints(UniqueConstraint("workspace_id"))
    enabled: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict)


class ProcessingResult(Owned):
    __tablename__ = "processing_results"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(["workspace_id", "job_id"], ["jobs.workspace_id", "jobs.id"]),
        ForeignKeyConstraint(
            ["workspace_id", "message_id"], ["messages.workspace_id", "messages.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "attachment_id"], ["attachments.workspace_id", "attachments.id"]
        ),
        UniqueConstraint("job_id"),
    )
    kind: Mapped[str] = mapped_column(String(30))
    job_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    message_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    attachment_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    source_sha256: Mapped[str] = mapped_column(String(64))
    provider_version: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, default="")
    search_text: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DataSource(Owned):
    __tablename__ = "data_sources"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(["owner_id"], ["users.id"]),
        UniqueConstraint("token_hash"),
        CheckConstraint("kind IN ('personal_files','wecom_archive')"),
    )
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    token_hash: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_cursor: Mapped[str | None] = mapped_column(String(200))
    failure_code: Mapped[str | None] = mapped_column(String(80))


class SourceReceipt(Owned):
    __tablename__ = "source_receipts"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(
            ["workspace_id", "source_id"], ["data_sources.workspace_id", "data_sources.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "batch_id"], ["ingest_batches.workspace_id", "ingest_batches.id"]
        ),
        UniqueConstraint("source_id", "cursor"),
    )
    source_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    batch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    cursor: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))


class OdooDelivery(Owned):
    __tablename__ = "odoo_deliveries"
    __table_args__ = owned_constraints(
        ForeignKeyConstraint(
            ["workspace_id", "entity_id"],
            ["entity_assertions.workspace_id", "entity_assertions.id"],
        ),
        ForeignKeyConstraint(["workspace_id", "job_id"], ["jobs.workspace_id", "jobs.id"]),
        UniqueConstraint("workspace_id", "idempotency_key"),
        UniqueConstraint("job_id"),
    )
    entity_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    job_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    instance_hash: Mapped[str] = mapped_column(String(64))
    target_model: Mapped[str] = mapped_column(String(100))
    values: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    remote_id: Mapped[int | None] = mapped_column(Integer)
    read_back: Mapped[dict[str, Any] | None] = mapped_column(JSON)


Index("ix_messages_timeline", Message.conversation_id, Message.sent_at, Message.id)
Index(
    "ix_messages_search_trgm",
    Message.search_text,
    postgresql_using="gin",
    postgresql_ops={"search_text": "gin_trgm_ops"},
)
