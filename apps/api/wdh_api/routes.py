import csv
import io
import json
import secrets
import unicodedata
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session
from wdh_adapters.files import Manifest, normalize
from wdh_domain.models import (
    Account,
    Attachment,
    AuditEvent,
    Contact,
    Conversation,
    Device,
    EntityAssertion,
    IngestBatch,
    Job,
    LoginSession,
    LoginThrottle,
    Membership,
    Message,
    MessageAttachment,
    MessageEvent,
    Observation,
    ProcessingResult,
    RawRecord,
    Review,
    SetupLock,
    SourceBlob,
    User,
    Workspace,
)
from wdh_storage.cas import ContentStore

from wdh_api.ingest import accept_upload
from wdh_api.security import (
    ApiError,
    Principal,
    as_utc,
    audit,
    csrf_token,
    digest,
    password_hash,
    password_matches,
    principal,
)

router = APIRouter(prefix="/api/v1")


def db(request: Request) -> Iterator[Session]:
    with request.app.state.factory() as session:
        yield session


DB = Annotated[Session, Depends(db)]


def scoped(session: Session, model: Any, object_id: str, who: Principal) -> Any:
    try:
        UUID(object_id)
    except ValueError as exc:
        raise ApiError(404, "NOT_FOUND", "未找到记录") from exc
    row = session.scalar(
        select(model).where(model.id == object_id, model.workspace_id == who.workspace_id)
    )
    if not row:
        raise ApiError(404, "NOT_FOUND", "未找到记录")
    return row


def columns(row: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in (exclude or set())
    }


def page(rows: list[Any], limit: int, render: Any = columns) -> dict[str, Any]:
    return {
        "items": [render(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=200)

    @field_validator("username")
    @classmethod
    def username_normalized(cls, value: str) -> str:
        result = unicodedata.normalize("NFKC", value).strip().casefold()
        if len(result) < 3 or any(ord(c) < 32 for c in result):
            raise ValueError("INVALID_USERNAME")
        return result


class Setup(Credentials):
    workspace_name: str = Field(default="我的工作空间", min_length=1, max_length=200)


class NewUser(Credentials):
    role: Literal["reader", "reviewer", "admin"] = "reader"


class Resolve(BaseModel):
    action: Literal["merge", "reject", "defer"]
    reason: str = Field(min_length=3, max_length=2000)


class Privacy(BaseModel):
    privacy_scope: Literal["private", "business_approved"]


class BackupRequest(BaseModel):
    password: str = Field(min_length=16, max_length=200)


class ExtractRequest(BaseModel):
    message_id: str


class EntityReview(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=2000)
    corrections: dict[str, str] = Field(default_factory=dict)


class DryRunRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=1, max_length=100)


@router.post("/entities/extract", tags=["entities"], status_code=201)
def extract_entity(data: ExtractRequest, request: Request, session: DB) -> dict[str, Any]:
    from wdh_api.entities import candidate_key, quotation_candidate

    who = principal(request, session, "reviewer")
    session.scalar(select(Workspace).where(Workspace.id == who.workspace_id).with_for_update())
    payload, evidence = quotation_candidate(session, who, data.message_id)
    key = candidate_key(data.message_id, payload)
    row = session.scalar(
        select(EntityAssertion).where(
            EntityAssertion.workspace_id == who.workspace_id, EntityAssertion.extraction_key == key
        )
    )
    if not row:
        row = EntityAssertion(
            workspace_id=who.workspace_id,
            entity_type="quotation",
            extraction_key=key,
            extractor_version="local-rules-1.0.0",
            payload=payload,
            evidence=evidence,
        )
        session.add(row)
        session.flush()
        audit(session, who, "entity.candidate", row.id, extractor="local-rules-1.0.0")
        session.commit()
    return columns(row)


@router.get("/entities", tags=["entities"])
def entities(
    request: Request, session: DB, limit: int = Query(50, ge=1, le=100), cursor: str | None = None
) -> dict[str, Any]:
    from wdh_api.entities import evidence_message

    who = principal(request, session)
    query = select(EntityAssertion).where(EntityAssertion.workspace_id == who.workspace_id)
    if cursor:
        scoped(session, EntityAssertion, cursor, who)
        query = query.where(EntityAssertion.id > cursor)
    rows = []
    for row in session.scalars(query.order_by(EntityAssertion.id).execution_options(yield_per=100)):
        try:
            if not row.evidence:
                continue
            for message_id in {item["message_id"] for item in row.evidence}:
                evidence_message(session, who, message_id)
        except ApiError:
            continue
        rows.append(row)
        if len(rows) > limit:
            break
    return page(rows, limit)


@router.post("/entities/{entity_id}/approve", tags=["entities"])
def approve_entity(
    entity_id: str, data: EntityReview, request: Request, session: DB
) -> dict[str, Any]:
    from wdh_api.entities import verified_payload

    who = principal(request, session, "reviewer")
    row = scoped(session, EntityAssertion, entity_id, who)
    session.refresh(row, with_for_update=True)
    if row.review_status != "pending":
        raise ApiError(409, "ALREADY_REVIEWED", "该候选已审核，保留既有批准记录")
    if data.decision == "approve":
        row.approved_payload = verified_payload(session, who, row, data.corrections)
        row.approved_by, row.approved_at = who.user_id, datetime.now(UTC)
        row.review_status = "approved"
    else:
        row.review_status = "rejected"
    audit(
        session,
        who,
        "entity." + data.decision,
        row.id,
        reason=data.reason,
        corrected_fields=sorted(data.corrections),
    )
    session.commit()
    return columns(row)


@router.post("/integrations/odoo/dry-run", tags=["integrations"])
def odoo_dry_run(data: DryRunRequest, request: Request, session: DB) -> dict[str, Any]:
    from wdh_api.entities import verified_payload

    who = principal(request, session, "reviewer")
    plans = []
    for id in dict.fromkeys(data.entity_ids):
        row = scoped(session, EntityAssertion, id, who)
        if row.review_status != "approved" or not row.approved_payload:
            raise ApiError(409, "APPROVAL_REQUIRED", "仅已审核批准的业务事实可进入同步预览")
        values = verified_payload(session, who, row)
        plans.append(
            {
                "entity_id": row.id,
                "target_model": {
                    "quotation": "purchase.order",
                    "purchase_intent": "purchase.order",
                    "customer": "res.partner",
                    "supplier": "res.partner",
                    "product": "product.template",
                    "order_candidate": "sale.order",
                }.get(row.entity_type),
                "state": "draft"
                if row.entity_type in {"quotation", "purchase_intent", "order_candidate"}
                else None,
                "action": "requires_verified_mapping",
                "source_values": values,
                "idempotency_key": digest(f"{who.workspace_id}:{row.id}:{row.entity_type}:v1"),
                "remote_id": None,
                "blockers": [
                    "未连接经授权的 Odoo CE 测试实例",
                    "需确认供应商、产品、币种和采购单位映射",
                ],
            }
        )
    audit(session, who, "odoo.dry_run", entity_count=len(plans))
    session.commit()
    return {"dry_run": True, "remote_writes": False, "connection_verified": False, "plans": plans}


@router.post("/backups", tags=["admin"])
def backup_download(data: BackupRequest, request: Request, session: DB) -> FileResponse:
    from wdh_api.backup import create_backup

    who = principal(request, session, "admin")
    settings = request.app.state.settings
    destination = settings.data_root / "exports" / f"backup-{uuid4().hex}.wdhbak"
    result = create_backup(
        request.app.state.engine,
        ContentStore(settings.data_root, settings.import_max_bytes),
        destination,
        data.password,
        workspace_id=who.workspace_id,
    )
    audit(
        session,
        who,
        "backup.created",
        destination.stem,
        objects=result["objects"],
        sha256=result["sha256"],
    )
    session.commit()
    return FileResponse(
        destination, filename="wechat-data-hub.wdhbak", media_type="application/octet-stream"
    )


def login_response(
    request: Request, response: Response, session: Session, user: User, member: Membership
) -> dict[str, Any]:
    token = secrets.token_urlsafe(48)
    expires = datetime.now(UTC) + timedelta(hours=request.app.state.settings.session_hours)
    session.add(
        LoginSession(
            workspace_id=member.workspace_id,
            user_id=user.id,
            token_hash=digest(token),
            expires_at=expires,
        )
    )
    who = Principal(user.id, member.workspace_id, member.role, user.username)
    audit(session, who, "auth.login")
    session.commit()
    response.set_cookie(
        "wdh_session",
        token,
        httponly=True,
        samesite="strict",
        secure=request.app.state.settings.cookie_secure,
        max_age=request.app.state.settings.session_hours * 3600,
        path="/",
    )
    return {
        "user": {"id": user.id, "username": user.username},
        "workspace_id": member.workspace_id,
        "role": member.role,
        "csrf_token": csrf_token(token),
    }


@router.get("/auth/status", tags=["auth"])
def auth_status(session: DB) -> dict[str, bool]:
    return {"setup_required": not bool(session.scalar(select(func.count()).select_from(User)))}


@router.post("/auth/setup", tags=["auth"], status_code=201)
def setup(data: Setup, request: Request, response: Response, session: DB) -> dict[str, Any]:
    # UPDATE is the atomic once-only gate, including on SQLite used in integration tests.
    claimed = session.execute(
        update(SetupLock)
        .where(SetupLock.id == 1, SetupLock.consumed.is_(False))
        .values(consumed=True)
        .returning(SetupLock.id)
    ).scalar()
    if not claimed:
        raise ApiError(409, "ALREADY_INITIALIZED", "工作空间已初始化，请登录")
    workspace = Workspace(name=data.workspace_name)
    user = User(username=data.username, password_hash=password_hash(data.password))
    session.add_all([workspace, user])
    session.flush()
    member = Membership(workspace_id=workspace.id, user_id=user.id, role="admin")
    session.add(member)
    session.flush()
    return login_response(request, response, session, user, member)


@router.post("/auth/login", tags=["auth"])
def login(data: Credentials, request: Request, response: Response, session: DB) -> dict[str, Any]:
    key = digest(f"{request.client.host if request.client else 'local'}:{data.username}")
    throttle = session.get(LoginThrottle, key, with_for_update=True)
    now = datetime.now(UTC)
    if not throttle:
        throttle = LoginThrottle(key=key, attempts=0, window_start=now)
        session.add(throttle)
        session.flush()
    if as_utc(throttle.window_start) < now - timedelta(minutes=15):
        throttle.attempts, throttle.window_start = 0, now
    if throttle.attempts >= 8:
        raise ApiError(429, "LOGIN_RATE_LIMIT", "尝试次数过多，请15分钟后重试")
    user = session.scalar(select(User).where(User.username == data.username))
    # Use equal-cost hashing for unknown users; no credential or message data is logged.
    dummy = "scrypt-v1$" + "00" * 16 + "$" + "00" * 32
    valid = password_matches(data.password, user.password_hash if user else dummy)
    if not user or not user.is_active or not valid:
        throttle.attempts += 1
        session.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码不正确")
    member = session.scalar(
        select(Membership)
        .where(Membership.user_id == user.id)
        .order_by(Membership.created_at)
        .limit(1)
    )
    if not member:
        raise ApiError(403, "NO_WORKSPACE", "没有可访问的工作空间")
    throttle.attempts = 0
    return login_response(request, response, session, user, member)


@router.post("/auth/logout", tags=["auth"])
def logout(request: Request, response: Response, session: DB) -> dict[str, bool]:
    who = principal(request, session)
    current = session.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == digest(request.cookies.get("wdh_session", ""))
        )
    )
    if current:
        session.delete(current)
    audit(session, who, "auth.logout")
    session.commit()
    response.delete_cookie("wdh_session", path="/")
    return {"ok": True}


@router.get("/me", tags=["auth"])
def me(request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session)
    workspace = session.get(Workspace, who.workspace_id)
    return {
        "user": {"id": who.user_id, "username": who.username},
        "role": who.role,
        "workspace_id": who.workspace_id,
        "workspace_name": workspace.name if workspace else "",
        "csrf_token": csrf_token(request.cookies["wdh_session"]),
    }


@router.get("/users", tags=["admin"])
def users(request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    rows = session.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == who.workspace_id)
    ).all()
    return {
        "items": [
            {
                "id": user.id,
                "username": user.username,
                "role": member.role,
                "is_active": user.is_active,
            }
            for user, member in rows
        ]
    }


@router.post("/users", tags=["admin"], status_code=201)
def create_user(data: NewUser, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    if session.scalar(select(User.id).where(User.username == data.username)):
        raise ApiError(409, "USERNAME_EXISTS", "用户名已存在")
    user = User(username=data.username, password_hash=password_hash(data.password))
    session.add(user)
    session.flush()
    session.add(Membership(workspace_id=who.workspace_id, user_id=user.id, role=data.role))
    audit(session, who, "user.created", user.id, role=data.role)
    session.commit()
    return {"id": user.id, "username": user.username, "role": data.role}


@router.get("/overview", tags=["browse"])
def overview(request: Request, session: DB) -> dict[str, Any]:
    from wdh_api import processing

    who = principal(request, session)

    def count(model: Any, *conditions: Any) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.workspace_id == who.workspace_id, *conditions)
            )
            or 0
        )

    return {
        "messages": count(Message, Message.merged_into.is_(None)),
        "conversations": count(Conversation),
        "attachments": count(Attachment),
        "devices": count(Device),
        "pending_reviews": count(Review, Review.status == "pending"),
        "imports": count(IngestBatch),
        "running_jobs": count(Job, Job.status.in_(["queued", "running", "failed_retryable"])),
        "accounts": [
            columns(row)
            for row in session.scalars(
                select(Account).where(Account.workspace_id == who.workspace_id)
            )
        ],
        "sources": [
            columns(row)
            for row in session.scalars(
                select(Device).where(Device.workspace_id == who.workspace_id)
            )
        ],
        "features": {
            "ocr": processing.enabled(session, request.app.state.settings, who.workspace_id, "ocr"),
            "asr": processing.enabled(session, request.app.state.settings, who.workspace_id, "asr"),
            "embeddings": processing.enabled(
                session, request.app.state.settings, who.workspace_id, "embedding"
            ),
            "llm": processing.enabled(session, request.app.state.settings, who.workspace_id, "llm"),
            "odoo": False,
        },
    }


@router.post("/imports", tags=["imports"], status_code=202)
def upload(
    request: Request,
    session: DB,
    file: Annotated[UploadFile, File()],
    manifest: Annotated[str | None, Form()] = None,
    source: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    who = principal(request, session, "admin")
    config = request.app.state.settings
    if manifest is not None and len(manifest.encode()) > 1_048_576:
        raise ApiError(400, "MANIFEST_TOO_LARGE", "清单过大")
    store = ContentStore(config.data_root, config.import_max_bytes)
    source_data = json.loads(source) if source else None
    if source_data is not None and (not isinstance(source_data, dict) or manifest is not None):
        raise ApiError(400, "INVALID_SOURCE_METADATA", "请选择来源声明或导入清单其中一种方式")
    return accept_upload(
        session,
        store,
        who,
        file.file,
        manifest.encode() if manifest else None,
        file.filename or "upload",
        config.upload_max_files,
        config.import_max_bytes,
        source_data,
    )


@router.get("/imports", tags=["imports"])
def imports(
    request: Request, session: DB, limit: int = Query(50, ge=1, le=100), cursor: str | None = None
) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    query = select(IngestBatch).where(IngestBatch.workspace_id == who.workspace_id)
    if cursor:
        scoped(session, IngestBatch, cursor, who)
        query = query.where(IngestBatch.id > cursor)
    rows = list(session.scalars(query.order_by(IngestBatch.id).limit(limit + 1)))

    def render(batch: IngestBatch) -> dict[str, Any]:
        counters = {
            key: value
            for key, value in session.execute(
                select(RawRecord.parse_status, func.count())
                .where(RawRecord.batch_id == batch.id, RawRecord.workspace_id == who.workspace_id)
                .group_by(RawRecord.parse_status)
            )
        }
        job = session.scalar(
            select(Job).where(
                Job.batch_id == batch.id, Job.workspace_id == who.workspace_id, Job.kind == "ingest"
            )
        )
        return {
            **columns(batch, {"manifest"}),
            "source": {
                key: batch.manifest.get(key)
                for key in (
                    "export_id",
                    "account_ref",
                    "device_ref",
                    "platform",
                    "exporter_name",
                    "exporter_version",
                    "exported_at",
                    "coverage_notes",
                )
            },
            "job": columns(job, {"lease_token", "payload"}) if job else None,
            "progress": {
                "processed": sum(counters.values()),
                "normalized": counters.get("normalized", 0),
                "quarantined": counters.get("quarantined", 0),
            },
        }

    return page(rows, limit, render)


@router.get("/imports/{batch_id}/coverage", tags=["imports"])
def coverage(batch_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    batch = scoped(session, IngestBatch, batch_id, who)
    statuses: dict[str, int] = {
        key: value
        for key, value in session.execute(
            select(RawRecord.parse_status, func.count())
            .where(RawRecord.batch_id == batch.id, RawRecord.workspace_id == who.workspace_id)
            .group_by(RawRecord.parse_status)
        ).all()
    }
    types: dict[str, int] = {
        key: value
        for key, value in session.execute(
            select(Message.message_type, func.count())
            .join(Observation, Observation.message_id == Message.id)
            .where(Observation.batch_id == batch.id, Message.workspace_id == who.workspace_id)
            .group_by(Message.message_type)
        ).all()
    }
    media: dict[str, int] = {
        key: value
        for key, value in session.execute(
            select(Attachment.availability, func.count())
            .join(MessageAttachment, MessageAttachment.attachment_id == Attachment.id)
            .join(RawRecord, RawRecord.id == MessageAttachment.raw_record_id)
            .where(RawRecord.batch_id == batch.id, RawRecord.workspace_id == who.workspace_id)
            .group_by(Attachment.availability)
        ).all()
    }
    return {
        "import_id": batch.id,
        "status": batch.batch_status,
        "records": sum(statuses.values()),
        "schema_statuses": statuses,
        "message_types": types,
        "media": media,
        "source": {key: value for key, value in batch.manifest.items() if key != "_archive"},
        "completeness": "observable-export-only",
    }


@router.get("/imports/{batch_id}/errors", tags=["imports"])
def errors(
    batch_id: str,
    request: Request,
    session: DB,
    limit: int = Query(100, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    who = principal(request, session, "admin")
    scoped(session, IngestBatch, batch_id, who)
    query = select(RawRecord).where(
        RawRecord.batch_id == batch_id,
        RawRecord.workspace_id == who.workspace_id,
        RawRecord.parse_status == "quarantined",
    )
    if cursor:
        scoped(session, RawRecord, cursor, who)
        query = query.where(RawRecord.id > cursor)
    rows = list(session.scalars(query.order_by(RawRecord.id).limit(limit + 1)))
    audit(session, who, "import.errors_read", batch_id)
    session.commit()
    return page(
        rows,
        limit,
        lambda row: {
            "id": row.id,
            "locator": row.source_record_locator,
            "errors": row.parse_errors,
            "sha256": row.raw_sha256,
        },
    )


@router.post("/imports/{batch_id}/retry", tags=["imports"], status_code=202)
def retry(batch_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    scoped(session, IngestBatch, batch_id, who)
    job = session.scalar(
        select(Job)
        .where(Job.workspace_id == who.workspace_id, Job.batch_id == batch_id, Job.kind == "ingest")
        .with_for_update()
    )
    if not job:
        raise ApiError(404, "NOT_FOUND", "未找到任务")
    if job.status in {"dead_letter", "cancelled", "failed_permanent", "failed_retryable"}:
        job.status, job.failure_code = "queued", None
        job.attempt_count, job.lease_token, job.next_retry_at = 0, None, None
        audit(session, who, "import.retry", batch_id)
        session.commit()
    return {"job_id": job.id, "status": job.status}


@router.post("/jobs/{job_id}/cancel", tags=["imports"])
def cancel(job_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    job = scoped(session, Job, job_id, who)
    session.refresh(job, with_for_update=True)
    if job.status not in {"completed", "cancelled"}:
        job.status, job.lease_token = "cancelled", None
        if job.batch_id:
            batch = scoped(session, IngestBatch, job.batch_id, who)
            batch.batch_status = "cancelled"
        audit(session, who, "job.cancelled", job.id)
        session.commit()
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs/{job_id}", tags=["imports"])
def job_status(job_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    return columns(scoped(session, Job, job_id, who), {"lease_token", "payload"})


@router.post("/imports/{batch_id}/reprocess-preview", tags=["imports"])
def preview(
    batch_id: str,
    request: Request,
    session: DB,
    limit: int = Query(100, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    who = principal(request, session, "admin")
    batch = scoped(session, IngestBatch, batch_id, who)
    manifest = Manifest.model_validate(batch.manifest)
    query = select(RawRecord).where(
        RawRecord.batch_id == batch_id, RawRecord.workspace_id == who.workspace_id
    )
    if cursor:
        scoped(session, RawRecord, cursor, who)
        query = query.where(RawRecord.id > cursor)
    rows = list(session.scalars(query.order_by(RawRecord.id).limit(limit + 1)))

    def render(raw: RawRecord) -> dict[str, Any]:
        if raw.raw_payload is None:
            return {"id": raw.id, "status": "unparseable", "changed": False}
        try:
            result = normalize(raw.raw_payload, manifest)
            current = session.scalar(
                select(Message)
                .join(Observation, Observation.message_id == Message.id)
                .where(
                    Observation.raw_record_id == raw.id, Message.workspace_id == who.workspace_id
                )
            )
            return {
                "id": raw.id,
                "status": "valid",
                "changed": current is None
                or current.body_text != result["body_text"]
                or current.message_type != result["message_type"],
            }
        except ValueError:
            return {"id": raw.id, "status": "quarantined", "changed": False}

    audit(session, who, "import.preview", batch_id)
    result = page(rows, limit, render)
    session.commit()
    return {**result, "normalization_version": "1.0.0", "dry_run": True}


@router.get("/conversations", tags=["browse"])
def conversations(
    request: Request,
    session: DB,
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    who = principal(request, session)
    query = select(Conversation).where(Conversation.workspace_id == who.workspace_id)
    if q:
        query = query.where(Conversation.title.contains(q[:200], autoescape=True))
    if cursor:
        scoped(session, Conversation, cursor, who)
        query = query.where(Conversation.id > cursor)
    rows = list(session.scalars(query.order_by(Conversation.id).limit(limit + 1)))

    def render(row: Conversation) -> dict[str, Any]:
        count = session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == row.id,
                Message.workspace_id == who.workspace_id,
                Message.merged_into.is_(None),
            )
        )
        latest = session.scalar(
            select(Message.body_text)
            .where(
                Message.conversation_id == row.id,
                Message.workspace_id == who.workspace_id,
                Message.merged_into.is_(None),
            )
            .order_by(Message.sent_at.desc().nulls_last(), Message.id)
            .limit(1)
        )
        return {**columns(row), "message_count": count, "preview": (latest or "")[:100]}

    return page(rows, limit, render)


def message_view(session: Session, message: Message) -> dict[str, Any]:
    result = columns(message, {"search_text", "strong_key", "weak_key", "content_signature"})
    sender = session.get(Contact, message.sender_contact_id) if message.sender_contact_id else None
    result["sender"] = sender.display_name if sender else "发送者未确认"
    result["observation_count"] = session.scalar(
        select(func.count())
        .select_from(Observation)
        .where(
            Observation.message_id == message.id, Observation.workspace_id == message.workspace_id
        )
    )
    media = session.execute(
        select(Attachment, MessageAttachment)
        .join(MessageAttachment, MessageAttachment.attachment_id == Attachment.id)
        .where(
            MessageAttachment.message_id == message.id,
            Attachment.workspace_id == message.workspace_id,
        )
    ).all()
    result["attachments"] = [
        {
            **columns(attachment),
            "source_path": link.original_media_path,
            "raw_record_id": link.raw_record_id,
        }
        for attachment, link in media
    ]
    result["processing_results"] = [
        {
            **columns(row, {"details", "search_text"}),
            "text": row.text[:1000],
            "details": {},
            "excerpt_truncated": len(row.text) > 1000,
        }
        for row in session.scalars(
            select(ProcessingResult)
            .join(Job, Job.id == ProcessingResult.job_id)
            .where(
                ProcessingResult.workspace_id == message.workspace_id,
                ProcessingResult.message_id == message.id,
                ProcessingResult.kind.in_(["ocr", "asr"]),
                Job.status == "completed",
            )
        )
    ]
    return result


def timeline_query(session: Session, who: Principal, query: Any, cursor: str | None) -> Any:
    if cursor:
        previous = scoped(session, Message, cursor, who)
        if previous.sent_at is None:
            query = query.where(Message.sent_at.is_(None), Message.id > previous.id)
        else:
            query = query.where(
                or_(
                    Message.sent_at > previous.sent_at,
                    and_(Message.sent_at == previous.sent_at, Message.id > previous.id),
                    Message.sent_at.is_(None),
                )
            )
    return query.order_by(Message.sent_at.asc().nulls_last(), Message.id)


@router.get("/conversations/{conversation_id}/messages", tags=["browse"])
def messages(
    conversation_id: str,
    request: Request,
    session: DB,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    who = principal(request, session)
    scoped(session, Conversation, conversation_id, who)
    query = select(Message).where(
        Message.workspace_id == who.workspace_id,
        Message.conversation_id == conversation_id,
        Message.merged_into.is_(None),
    )
    rows = list(session.scalars(timeline_query(session, who, query, cursor).limit(limit + 1)))
    return page(rows, limit, lambda row: message_view(session, row))


@router.get("/messages/{message_id}", tags=["browse"])
def message_detail(message_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session)
    message = scoped(session, Message, message_id, who)
    observations = session.scalars(
        select(Observation).where(
            Observation.message_id == message.id, Observation.workspace_id == who.workspace_id
        )
    ).all()
    sources = []
    for observation in observations:
        raw = scoped(session, RawRecord, observation.raw_record_id, who)
        batch = scoped(session, IngestBatch, observation.batch_id, who)
        device = scoped(session, Device, observation.device_id, who)
        blob = scoped(session, SourceBlob, batch.main_blob_id, who)
        sources.append(
            {
                **columns(observation),
                "raw": columns(raw),
                "batch": {
                    "id": batch.id,
                    "sha256": blob.sha256,
                    "adapter_id": batch.adapter_id,
                    "adapter_version": batch.adapter_version,
                },
                "device": columns(device),
            }
        )
    events = list(
        session.scalars(
            select(MessageEvent).where(
                MessageEvent.message_id == message.id, MessageEvent.workspace_id == who.workspace_id
            )
        )
    )
    audit(session, who, "message.source_read", message.id)
    session.commit()
    return {
        **message_view(session, message),
        "privacy_scope": scoped(session, Conversation, message.conversation_id, who).privacy_scope,
        "observations": sources,
        "events": [columns(event) for event in events],
    }


@router.get("/contacts", tags=["browse"])
def contacts(
    request: Request, session: DB, limit: int = Query(50, ge=1, le=100), cursor: str | None = None
) -> dict[str, Any]:
    who = principal(request, session)
    query = select(Contact).where(Contact.workspace_id == who.workspace_id)
    if cursor:
        scoped(session, Contact, cursor, who)
        query = query.where(Contact.id > cursor)
    return page(list(session.scalars(query.order_by(Contact.id).limit(limit + 1))), limit)


@router.patch("/conversations/{conversation_id}/privacy", tags=["admin"])
def privacy(conversation_id: str, data: Privacy, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    conversation = scoped(session, Conversation, conversation_id, who)
    conversation.privacy_scope = data.privacy_scope
    audit(session, who, "conversation.privacy", conversation.id, scope=data.privacy_scope)
    session.commit()
    return columns(conversation)


@router.get("/search", tags=["search"])
def search(
    request: Request,
    session: DB,
    q: str = Query("", max_length=500),
    conversation_id: str | None = None,
    account_id: str | None = None,
    device_id: str | None = None,
    sender_id: str | None = None,
    message_type: str | None = None,
    has_attachment: bool | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    who = principal(request, session)
    query = select(Message).where(
        Message.workspace_id == who.workspace_id, Message.merged_into.is_(None)
    )
    for term in unicodedata.normalize("NFKC", q).casefold().split():
        derived = (
            select(ProcessingResult.id)
            .join(Job, Job.id == ProcessingResult.job_id)
            .where(
                ProcessingResult.workspace_id == who.workspace_id,
                ProcessingResult.message_id == Message.id,
                ProcessingResult.kind.in_(["ocr", "asr"]),
                Job.status == "completed",
                ProcessingResult.search_text.contains(term, autoescape=True),
            )
            .exists()
        )
        query = query.where(or_(Message.search_text.contains(term, autoescape=True), derived))
    for key, value, model in (
        ("conversation_id", conversation_id, Conversation),
        ("account_id", account_id, Account),
        ("sender_contact_id", sender_id, Contact),
    ):
        if value:
            row = scoped(session, model, value, who)
            if key == "sender_contact_id":
                visited: set[str] = set()
                while row.linked_contact_id:
                    if row.id in visited:
                        raise ApiError(409, "IDENTITY_CYCLE", "联系人关联需要管理员修复")
                    visited.add(row.id)
                    row = scoped(session, Contact, row.linked_contact_id, who)
                linked = (
                    select(Contact.id)
                    .where(Contact.workspace_id == who.workspace_id, Contact.id == row.id)
                    .cte(name="linked_contacts", recursive=True)
                )
                linked = linked.union(
                    select(Contact.id).where(
                        Contact.workspace_id == who.workspace_id,
                        Contact.linked_contact_id == linked.c.id,
                    )
                )
                query = query.where(Message.sender_contact_id.in_(select(linked.c.id)))
            else:
                query = query.where(getattr(Message, key) == value)
    if device_id:
        scoped(session, Device, device_id, who)
        query = query.where(
            Message.id.in_(
                select(Observation.message_id).where(
                    Observation.workspace_id == who.workspace_id, Observation.device_id == device_id
                )
            )
        )
    if message_type:
        query = query.where(Message.message_type == message_type)
    if start:
        query = query.where(Message.sent_at >= as_utc(start))
    if end:
        query = query.where(Message.sent_at <= as_utc(end))
    if has_attachment is not None:
        exists = (
            select(MessageAttachment.id)
            .where(
                MessageAttachment.message_id == Message.id,
                MessageAttachment.workspace_id == who.workspace_id,
            )
            .exists()
        )
        query = query.where(exists if has_attachment else ~exists)
    rows = list(session.scalars(timeline_query(session, who, query, cursor).limit(limit + 1)))
    return page(rows, limit, lambda row: message_view(session, row))


@router.get("/attachments/{attachment_id}/download", tags=["browse"])
def attachment_download(attachment_id: str, request: Request, session: DB) -> StreamingResponse:
    who = principal(request, session)
    attachment = scoped(session, Attachment, attachment_id, who)
    if attachment.availability != "available" or not attachment.sha256:
        raise ApiError(404, "ATTACHMENT_MISSING", "源文件未提供该附件")
    store = ContentStore(
        request.app.state.settings.data_root, request.app.state.settings.import_max_bytes
    )
    # Validate before starting a successful HTTP response, then keep a verified FD during streaming.
    digest_value = attachment.sha256
    context = store.open(digest_value)
    stream = context.__enter__()

    def chunks() -> Iterator[bytes]:
        try:
            while chunk := stream.read(1024 * 1024):
                yield chunk
        finally:
            context.__exit__(None, None, None)

    audit(session, who, "attachment.download", attachment.id)
    session.commit()
    return StreamingResponse(
        chunks(),
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="attachment-{attachment.id}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/reviews", tags=["reviews"])
def reviews(
    request: Request,
    session: DB,
    status: str = "pending",
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    query = select(Review).where(Review.workspace_id == who.workspace_id, Review.status == status)
    if cursor:
        scoped(session, Review, cursor, who)
        query = query.where(Review.id > cursor)
    rows = list(session.scalars(query.order_by(Review.id).limit(limit + 1)))

    def render(row: Review) -> dict[str, Any]:
        return {
            **columns(row),
            "messages": [
                message_view(session, scoped(session, Message, id, who))
                for id in row.payload.get("message_ids", [])
            ],
            "contacts": [
                columns(scoped(session, Contact, id, who))
                for id in row.payload.get("contact_ids", [])
            ],
        }

    return page(rows, limit, render)


@router.post("/reviews/{review_id}/resolve", tags=["reviews"])
def resolve(review_id: str, data: Resolve, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    row = scoped(session, Review, review_id, who)
    session.refresh(row, with_for_update=True)
    if row.status not in {"pending", "deferred"}:
        return columns(row)
    if data.action == "merge":
        if row.review_type == "conflict":
            raise ApiError(
                409, "CONFLICT_REQUIRES_DISTINCT_VERSIONS", "内容冲突需保留独立版本，可选择保留两条"
            )
        ids = row.payload.get("message_ids", [])
        if len(ids) == 2:
            target, source = [scoped(session, Message, id, who) for id in ids]
            if (
                target.account_id != source.account_id
                or target.conversation_id != source.conversation_id
            ):
                raise ApiError(409, "INCOMPATIBLE_MESSAGES", "不同账号或会话不能合并")
            if target.merged_into or source.merged_into:
                raise ApiError(409, "STALE_REVIEW", "记录已变更，请重新查看来源")
            session.execute(
                update(Observation)
                .where(
                    Observation.workspace_id == who.workspace_id,
                    Observation.message_id == source.id,
                )
                .values(message_id=target.id)
            )
            session.execute(
                update(MessageAttachment)
                .where(
                    MessageAttachment.workspace_id == who.workspace_id,
                    MessageAttachment.message_id == source.id,
                )
                .values(message_id=target.id)
            )
            session.execute(
                update(ProcessingResult)
                .where(
                    ProcessingResult.workspace_id == who.workspace_id,
                    ProcessingResult.message_id == source.id,
                )
                .values(message_id=target.id)
            )
            for entity in session.scalars(
                select(EntityAssertion).where(EntityAssertion.workspace_id == who.workspace_id)
            ):
                if any(item.get("message_id") == source.id for item in entity.evidence):
                    entity.evidence = [
                        {**item, "message_id": target.id, "merged_from_message_id": source.id}
                        if item.get("message_id") == source.id
                        else item
                        for item in entity.evidence
                    ]
            session.execute(
                update(Message)
                .where(Message.workspace_id == who.workspace_id, Message.reply_to_id == source.id)
                .values(reply_to_id=target.id)
            )
            source.merged_into, target.merge_status = target.id, "verified"
        contacts = row.payload.get("contact_ids", [])
        if len(contacts) == 2:
            target_contact, source_contact = [scoped(session, Contact, id, who) for id in contacts]
            if target_contact.account_id != source_contact.account_id:
                raise ApiError(409, "INCOMPATIBLE_CONTACTS", "不同账号不能关联联系人")
            if target_contact.linked_contact_id or source_contact.linked_contact_id:
                raise ApiError(409, "STALE_IDENTITY_REVIEW", "联系人已有身份关联，请重新检查证据")
            source_contact.linked_contact_id = target_contact.id
    row.status = "deferred" if data.action == "defer" else "resolved"
    row.decision = data.model_dump()
    row.reviewer_id, row.reviewed_at = who.user_id, datetime.now(UTC)
    audit(session, who, "review." + data.action, row.id, reason=data.reason)
    session.commit()
    return columns(row)


@router.get("/audit", tags=["admin"])
def audit_events(
    request: Request, session: DB, limit: int = Query(50, ge=1, le=100), cursor: str | None = None
) -> dict[str, Any]:
    who = principal(request, session, "admin")
    query = select(AuditEvent).where(AuditEvent.workspace_id == who.workspace_id)
    if cursor:
        scoped(session, AuditEvent, cursor, who)
        query = query.where(AuditEvent.id > cursor)
    return page(list(session.scalars(query.order_by(AuditEvent.id).limit(limit + 1))), limit)


def csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


@router.get("/exports/messages", tags=["admin"])
def export_messages(
    request: Request,
    session: DB,
    format: Literal["jsonl", "csv"] = "jsonl",
    conversation_id: str | None = None,
) -> StreamingResponse:
    who = principal(request, session, "admin")
    if conversation_id:
        scoped(session, Conversation, conversation_id, who)
    audit(session, who, "messages.export", conversation_id, format=format)
    session.commit()
    factory = request.app.state.factory

    def generate() -> Iterator[str]:
        with factory() as export_session:
            query = select(Message).where(
                Message.workspace_id == who.workspace_id, Message.merged_into.is_(None)
            )
            if conversation_id:
                query = query.where(Message.conversation_id == conversation_id)
            rows = export_session.scalars(
                query.order_by(Message.id).execution_options(yield_per=500)
            )
            fields = [
                "id",
                "conversation_id",
                "sender_contact_id",
                "sent_at",
                "message_type",
                "body_text",
            ]
            if format == "csv":
                buffer = io.StringIO(newline="")
                writer = csv.writer(buffer)
                writer.writerow(fields)
                yield "\ufeff" + buffer.getvalue()
                for message in rows:
                    buffer.seek(0)
                    buffer.truncate()
                    writer.writerow([csv_safe(getattr(message, key)) for key in fields])
                    yield buffer.getvalue()
            else:
                for message in rows:
                    result = message_view(export_session, message)
                    result["source_observations"] = [
                        columns(row)
                        for row in export_session.scalars(
                            select(Observation).where(
                                Observation.message_id == message.id,
                                Observation.workspace_id == who.workspace_id,
                            )
                        )
                    ]
                    yield json.dumps(result, ensure_ascii=False, default=str) + "\n"

    return StreamingResponse(
        generate(),
        media_type="text/csv" if format == "csv" else "application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="messages.{format}"'},
    )


@router.get("/examples/bundle", tags=["imports"])
def example_bundle(request: Request, session: DB) -> StreamingResponse:
    who = principal(request, session, "admin")
    from wdh_api.demo import demo_zip

    data = demo_zip()
    audit(session, who, "examples.download")
    session.commit()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="synthetic-example.zip"'},
    )


@router.get("/integrations/odoo/status", tags=["integrations"])
def odoo_status(request: Request, session: DB) -> dict[str, Any]:
    from wdh_api.odoo import configured

    principal(request, session, "admin")
    settings = request.app.state.settings
    return {
        "enabled": settings.enable_odoo,
        "configured": configured(settings),
        "real_validation": "NOT_TESTED"
        if settings.enable_odoo and configured(settings)
        else "BLOCKED",
        "remote_writes_enabled": False,
    }


@router.post("/integrations/odoo/test", tags=["integrations"])
def odoo_test(request: Request, session: DB) -> dict[str, Any]:
    from wdh_api.odoo import OdooCheckError, check

    who = principal(request, session, "admin")
    try:
        report = check(request.app.state.settings)
    except OdooCheckError as exc:
        code = str(exc)
        audit(session, who, "odoo.handshake_failed", code=code)
        session.commit()
        raise ApiError(
            409 if code in {"ODOO_DISABLED", "ODOO_NOT_CONFIGURED", "ODOO_INVALID_URL"} else 502,
            code,
            "Odoo 只读验证未完成，请检查本地连接配置、实例和权限",
        ) from exc
    audit(session, who, "odoo.handshake", target_19_ce=report["target_19_ce"])
    session.commit()
    return report
