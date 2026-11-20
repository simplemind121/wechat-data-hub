"""Scoped collectors can only archive batches for their bound source, never browse chats."""

import hashlib
import secrets
import shutil
import zipfile
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from wdh_adapters.files import Manifest
from wdh_domain.models import DataSource, Job, Membership, SourceReceipt, User
from wdh_storage.cas import ContentStore

from wdh_api.ingest import accept_upload
from wdh_api.routes import DB, columns, scoped
from wdh_api.security import ApiError, Principal, audit, digest, principal

router = APIRouter(prefix="/api/v1", tags=["sources"])
COLLECTOR_PATHS = {
    "/api/v1/collector/status",
    "/api/v1/collector/heartbeat",
    "/api/v1/collector/batches",
}


class SourceMetadata(BaseModel):
    account_ref: str = Field(min_length=1, max_length=200)
    device_ref: str = Field(min_length=1, max_length=200)
    platform: Literal["ios", "macos", "windows", "other"] = "other"
    os_version: str = Field(default="unknown", max_length=100)
    wechat_version: str = Field(default="unknown", max_length=100)
    exporter_name: str = Field(default="user-export", min_length=1, max_length=100)
    exporter_version: str = Field(default="unknown", max_length=100)
    original_timezone: str = "Asia/Shanghai"
    data_format: Literal["jsonl-v1", "json-v1", "csv-v1"] = "jsonl-v1"
    field_mapping: dict[str, str] = Field(default_factory=dict, max_length=30)
    json_root: Literal["array", "messages"] = "array"
    delimiter: Literal[",", ";", "\t"] = ","


class NewSource(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["personal_files", "wecom_archive"]
    metadata: SourceMetadata


class SourceState(BaseModel):
    enabled: bool


class Heartbeat(BaseModel):
    failure_code: str | None = Field(default=None, pattern=r"^[A-Z_]{1,80}$")


def view(row: DataSource) -> dict[str, Any]:
    return {**columns(row, {"token_hash", "owner_id"}), "credential_active": bool(row.token_hash)}


@router.post("/sources", status_code=201)
def create_source(data: NewSource, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    metadata = data.metadata.model_dump()
    if data.kind == "wecom_archive":
        metadata.update(
            exporter_name="wdh-wecom-finance",
            exporter_version="1.0.0",
            data_format="jsonl-v1",
            field_mapping={},
        )
    Manifest.model_validate(
        {
            **metadata,
            "schema_version": "1.0.0",
            "export_id": "validation",
            "exported_at": datetime.now(UTC),
            "payload_files": [{"path": "messages.jsonl", "size_bytes": 0, "sha256": "0" * 64}],
            "consent_scope": "authorized-export",
            "coverage_notes": "Source completeness requires independent validation",
        }
    )
    token = "wdhc_" + secrets.token_urlsafe(32)
    row = DataSource(
        workspace_id=who.workspace_id,
        owner_id=who.user_id,
        name=data.name,
        kind=data.kind,
        token_hash=digest(token),
        source_metadata=metadata,
    )
    session.add(row)
    session.flush()
    audit(session, who, "source.created", row.id, kind=row.kind)
    session.commit()
    return {"source": view(row), "token": token}


@router.get("/sources")
def list_sources(request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    return {
        "items": [
            view(row)
            for row in session.scalars(
                select(DataSource)
                .where(DataSource.workspace_id == who.workspace_id)
                .order_by(DataSource.created_at)
                .limit(100)
            )
        ]
    }


@router.post("/sources/{source_id}/state")
def source_state(
    source_id: str, data: SourceState, request: Request, session: DB
) -> dict[str, Any]:
    who = principal(request, session, "admin")
    row = scoped(session, DataSource, source_id, who)
    row.enabled = data.enabled
    audit(session, who, "source.state", row.id, enabled=row.enabled)
    session.commit()
    return view(row)


@router.post("/sources/{source_id}/rotate")
def rotate(source_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    row = scoped(session, DataSource, source_id, who)
    token = "wdhc_" + secrets.token_urlsafe(32)
    row.token_hash, row.owner_id = digest(token), who.user_id
    audit(session, who, "source.rotated", row.id)
    session.commit()
    return {"token": token}


def collector(request: Request, session: Session) -> DataSource:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer wdhc_") or len(authorization) > 200:
        raise ApiError(401, "COLLECTOR_UNAUTHENTICATED", "采集凭据无效")
    row = session.scalar(
        select(DataSource).where(DataSource.token_hash == digest(authorization[7:]))
    )
    if not row or not row.enabled:
        raise ApiError(401, "COLLECTOR_UNAUTHENTICATED", "采集凭据已暂停或失效")
    owner = session.get(User, row.owner_id)
    member = session.scalar(
        select(Membership).where(
            Membership.workspace_id == row.workspace_id,
            Membership.user_id == row.owner_id,
            Membership.role == "admin",
        )
    )
    if not owner or not owner.is_active or not member:
        raise ApiError(401, "COLLECTOR_UNAUTHENTICATED", "采集凭据所有者已失效")
    return row


@router.get("/collector/status")
def collector_status(request: Request, session: DB) -> dict[str, Any]:
    return view(collector(request, session))


@router.post("/collector/heartbeat")
def heartbeat(data: Heartbeat, request: Request, session: DB) -> dict[str, bool]:
    row = collector(request, session)
    row.last_seen_at, row.failure_code = datetime.now(UTC), data.failure_code
    session.commit()
    return {"ok": True}


@router.post("/collector/batches", status_code=202)
def collect_batch(
    request: Request,
    session: DB,
    file: Annotated[UploadFile, File()],
    cursor: Annotated[str, Form(min_length=1, max_length=200)],
    manifest: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    row = collector(request, session)
    config = request.app.state.settings
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if (
        size > config.import_max_bytes
        or size * 3 + 33_554_432 > shutil.disk_usage(config.data_root).free
    ):
        raise ApiError(413, "SIZE_LIMIT", "文件过大或可用空间不足")
    digestor = hashlib.sha256()
    while chunk := file.file.read(1_048_576):
        digestor.update(chunk)
    sha = digestor.hexdigest()
    file.file.seek(0)
    existing = session.scalar(
        select(SourceReceipt).where(
            SourceReceipt.source_id == row.id, SourceReceipt.cursor == cursor
        )
    )
    if existing:
        if existing.sha256 != sha:
            raise ApiError(409, "CURSOR_CONFLICT", "同一同步位置对应了不同文件")
        job = session.scalar(
            select(Job).where(Job.batch_id == existing.batch_id, Job.kind == "ingest")
        )
        return {
            "import_id": existing.batch_id,
            "job_id": job.id if job else None,
            "status": "already_ingested",
            "cursor": cursor,
        }
    if row.kind == "wecom_archive" and (
        not cursor.isdecimal() or (row.last_cursor and int(cursor) <= int(row.last_cursor))
    ):
        raise ApiError(409, "CURSOR_REGRESSION", "存档序号必须向前推进")
    if manifest:
        parsed = Manifest.model_validate_json(manifest)
    elif (file.filename or "").lower().endswith(".zip"):
        with zipfile.ZipFile(file.file) as archive:
            entries = [item for item in archive.infolist() if item.filename == "manifest.json"]
            if len(entries) != 1 or entries[0].file_size > 1_048_576:
                raise ApiError(400, "MANIFEST_REQUIRED", "采集 ZIP 根目录需有 manifest.json")
            parsed = Manifest.model_validate_json(archive.read(entries[0]))
        file.file.seek(0)
    else:
        parsed = None
    if parsed and any(
        getattr(parsed, key) != row.source_metadata[key]
        for key in ("account_ref", "device_ref", "exporter_name", "exporter_version")
    ):
        raise ApiError(403, "SOURCE_BINDING_MISMATCH", "文件来源与采集端绑定不符")
    if row.kind == "wecom_archive" and parsed is None:
        raise ApiError(400, "MANIFEST_REQUIRED", "企微存档需提供完整清单")
    who = Principal(row.owner_id, row.workspace_id, "admin", "collector")
    result = accept_upload(
        session,
        ContentStore(config.data_root, config.import_max_bytes),
        who,
        file.file,
        manifest.encode() if manifest else None,
        file.filename or "messages.jsonl",
        config.upload_max_files,
        config.import_max_bytes,
        None if parsed else {**row.source_metadata, "exported_at": datetime.now(UTC).isoformat()},
    )
    # A receipt means bytes + ingest job are durable, not that normalization succeeded.
    locked = session.scalar(
        select(DataSource)
        .where(DataSource.id == row.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise ApiError(401, "COLLECTOR_UNAUTHENTICATED", "数据源已失效")
    if not locked.enabled or locked.token_hash != digest(request.headers["authorization"][7:]):
        raise ApiError(401, "COLLECTOR_UNAUTHENTICATED", "采集凭据已暂停或失效")
    previous = session.scalar(
        select(SourceReceipt).where(
            SourceReceipt.source_id == row.id, SourceReceipt.cursor == cursor
        )
    )
    if previous:
        if previous.sha256 != sha:
            raise ApiError(409, "CURSOR_CONFLICT", "同步位置发生冲突")
    else:
        session.add(
            SourceReceipt(
                workspace_id=row.workspace_id,
                source_id=row.id,
                batch_id=result["import_id"],
                cursor=cursor,
                sha256=sha,
            )
        )
    if (
        row.kind != "wecom_archive"
        or not locked.last_cursor
        or int(cursor) > int(locked.last_cursor)
    ):
        locked.last_cursor = cursor
    locked.last_seen_at, locked.failure_code = datetime.now(UTC), None
    audit(session, who, "source.batch_archived", result["import_id"], source_id=row.id)
    session.commit()
    return {**result, "cursor": cursor}
