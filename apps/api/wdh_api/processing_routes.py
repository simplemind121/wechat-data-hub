"""Authenticated processing APIs; source selection is always scoped to a workspace and message."""

from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from wdh_domain.models import (
    Attachment,
    Conversation,
    Job,
    Message,
    MessageAttachment,
    ProcessingPolicy,
    ProcessingResult,
    Workspace,
)

from wdh_api import processing
from wdh_api.ingest import fingerprint
from wdh_api.routes import DB, columns, page, scoped
from wdh_api.security import ApiError, audit, principal

router = APIRouter(prefix="/api/v1", tags=["processing"])
Kind = Literal["ocr", "asr", "embedding", "llm"]


class ProcessSource(BaseModel):
    message_id: str
    attachment_id: str | None = None
    source_result_id: str | None = None


class ModuleChange(BaseModel):
    enabled: bool


def result_view(session: Any, result: ProcessingResult) -> dict[str, Any]:
    job = session.get(Job, result.job_id)
    return {**columns(result), "status": job.status, "failure_code": job.failure_code}


@router.get("/processing/capabilities")
def capabilities(request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session)
    settings = request.app.state.settings
    from wdh_api.models import catalog

    modules = {}
    for kind in processing.KINDS:
        module = processing.capability(settings, kind)
        job = session.scalar(
            select(Job)
            .where(
                Job.workspace_id == who.workspace_id,
                Job.kind == "model_install",
                Job.payload["module"].as_string() == kind,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        module["install_job"] = columns(job, {"payload", "lease_token"}) if job else None
        module["enabled"] = processing.enabled(session, settings, who.workspace_id, kind)
        module["installable"] = module.get("reason") == "MODEL_NOT_INSTALLED"
        module["download_bytes"] = sum(item["bytes"] for item in catalog()[kind]["files"])
        modules[kind] = module
    return {
        "modules": modules,
        "external_inference": False,
        "model_download_requires_network": True,
    }


@router.post("/processing/models/{kind}/install", status_code=202)
def model_install(kind: Kind, request: Request, session: DB) -> dict[str, Any]:
    import shutil

    from wdh_api.models import catalog, revision

    who = principal(request, session, "admin")
    settings = request.app.state.settings
    available = processing.capability(settings, kind)
    if available["available"]:
        return {"status": "already_installed", "job_id": None}
    if available["reason"] != "MODEL_NOT_INSTALLED":
        raise ApiError(
            409, "ENGINE_NOT_INSTALLED", "当前运行包缺少本地推理引擎，请使用包含识别模块的新版本"
        )
    required = sum(item["bytes"] for item in catalog()[kind]["files"])
    if required + 33_554_432 > shutil.disk_usage(settings.data_root).free:
        raise ApiError(507, "MODEL_STORAGE_LIMIT", "可用空间不足以安装模型，请扩容后重试")
    session.scalar(select(Workspace).where(Workspace.id == who.workspace_id).with_for_update())
    key = fingerprint([kind, revision(kind)])
    job = session.scalar(
        select(Job).where(
            Job.workspace_id == who.workspace_id,
            Job.kind == "model_install",
            Job.idempotency_key == key,
        )
    )
    if not job:
        job = Job(
            workspace_id=who.workspace_id,
            kind="model_install",
            idempotency_key=key,
            payload={"module": kind, "asset_revision": revision(kind)},
        )
        session.add(job)
    elif job.status not in {"queued", "running"}:
        job.status, job.failure_code, job.lease_token = "queued", None, None
        job.attempt_count, job.next_retry_at = 0, None
    audit(session, who, "model.install_requested", kind)
    session.commit()
    return {"job_id": job.id, "status": job.status}


@router.patch("/processing/modules/{kind}")
def module_change(kind: Kind, data: ModuleChange, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    session.scalar(select(Workspace).where(Workspace.id == who.workspace_id).with_for_update())
    settings = request.app.state.settings
    if data.enabled and not processing.capability(settings, kind)["available"]:
        raise ApiError(409, "PROVIDER_UNAVAILABLE", "识别引擎或模型尚未安装，请先完成本地模型安装")
    policy = session.scalar(
        select(ProcessingPolicy).where(ProcessingPolicy.workspace_id == who.workspace_id)
    )
    if not policy:
        policy = ProcessingPolicy(workspace_id=who.workspace_id, enabled={})
        session.add(policy)
    policy.enabled = {**policy.enabled, kind: data.enabled}
    if not data.enabled:
        session.execute(
            update(Job)
            .where(
                Job.workspace_id == who.workspace_id,
                Job.kind == kind,
                Job.status.in_(["queued", "running", "failed_retryable"]),
            )
            .values(status="cancelled", lease_token=None, lease_until=None)
        )
    elif kind == "embedding":
        from wdh_api.semantic import ensure_index

        try:
            ensure_index(session)
        except SQLAlchemyError as exc:
            session.rollback()
            raise ApiError(
                409, "VECTOR_NOT_READY", "数据库尚未安装向量组件，请升级到包含语义检索的数据库版本"
            ) from exc
    audit(session, who, "processing.module", kind, enabled=data.enabled)
    session.commit()
    return {"kind": kind, "enabled": data.enabled}


@router.post("/process/{kind}", status_code=202)
def process(kind: Kind, data: ProcessSource, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    session.scalar(select(Workspace).where(Workspace.id == who.workspace_id).with_for_update())
    message = scoped(session, Message, data.message_id, who)
    attachment = None
    source_id = None
    if kind in {"ocr", "asr"}:
        if not data.attachment_id:
            raise ApiError(422, "ATTACHMENT_REQUIRED", "请选择原始附件")
        attachment = scoped(session, Attachment, data.attachment_id, who)
        link = session.scalar(
            select(MessageAttachment).where(
                MessageAttachment.workspace_id == who.workspace_id,
                MessageAttachment.message_id == message.id,
                MessageAttachment.attachment_id == attachment.id,
            )
        )
        if not link:
            raise ApiError(404, "NOT_FOUND", "附件不属于这条消息")
        if attachment.availability != "available" or not attachment.sha256:
            raise ApiError(409, "ATTACHMENT_MISSING", "原始附件缺失，无法识别")
        allowed = processing.IMAGE_MIMES if kind == "ocr" else processing.AUDIO_MIMES
        if attachment.mime_type not in allowed:
            raise ApiError(415, "UNSUPPORTED_FORMAT", "附件格式不受当前本地引擎支持")
        if (attachment.byte_size or 0) > request.app.state.settings.processing_max_bytes:
            raise ApiError(413, "PROCESSING_SIZE_LIMIT", "附件超过本地识别大小限制")
        source_hash = attachment.sha256
    else:
        from wdh_api.ai import material, text_hash

        if data.source_result_id:
            source = scoped(session, ProcessingResult, data.source_result_id, who)
            if source.message_id != message.id:
                raise ApiError(404, "NOT_FOUND", "识别结果不属于这条消息")
            source_id = source.id
        try:
            source_text = material(session, who.workspace_id, message.id, source_id)
        except ValueError as exc:
            raise ApiError(
                403 if str(exc) == "PRIVATE_CONVERSATION" else 422,
                str(exc),
                "需有可用原文证据，并由管理员允许该会话进行业务处理",
            ) from exc
        if len(source_text) > (4000 if kind == "embedding" else 2000):
            raise ApiError(
                422,
                "SOURCE_TOO_LONG",
                "所选来源超过本地模型长度限制，请使用较短的原始消息或识别结果",
            )
        source_hash = text_hash(source_text)
    settings = request.app.state.settings
    if not processing.enabled(session, settings, who.workspace_id, kind):
        raise ApiError(409, "MODULE_DISABLED", "请先由管理员在设置中启用对应的本地识别模块")
    provider = processing.capability(settings, kind)
    if not provider["available"]:
        raise ApiError(409, "PROVIDER_UNAVAILABLE", "本地识别引擎或模型尚未就绪")
    key = fingerprint([kind, message.id, source_hash, source_id, provider["provider_version"]])
    job = session.scalar(
        select(Job).where(
            Job.workspace_id == who.workspace_id, Job.kind == kind, Job.idempotency_key == key
        )
    )
    if job:
        result = session.scalar(select(ProcessingResult).where(ProcessingResult.job_id == job.id))
        if not result:
            raise ApiError(409, "RESULT_MISSING", "任务结果索引需要管理员检查")
        return {"job_id": job.id, "result_id": result.id, "status": job.status}
    job = Job(
        workspace_id=who.workspace_id,
        kind=kind,
        idempotency_key=key,
        payload={
            "provider_version": provider["provider_version"],
            "source_result_id": source_id,
            "actor_id": who.user_id,
        },
    )
    session.add(job)
    session.flush()
    result = ProcessingResult(
        workspace_id=who.workspace_id,
        job_id=job.id,
        kind=kind,
        message_id=message.id,
        attachment_id=attachment.id if attachment else None,
        source_sha256=source_hash,
        provider_version=provider["provider_version"],
    )
    session.add(result)
    audit(session, who, "processing.queued", job.id, kind=kind, message_id=message.id)
    session.commit()
    return {"job_id": job.id, "result_id": result.id, "status": job.status}


@router.get("/processing/results/{result_id}")
def result_detail(result_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session)
    result = scoped(session, ProcessingResult, result_id, who)
    if result.kind in {"embedding", "llm"}:
        message = scoped(session, Message, result.message_id, who)
        if (
            scoped(session, Conversation, message.conversation_id, who).privacy_scope
            != "business_approved"
        ):
            raise ApiError(403, "PRIVATE_CONVERSATION", "当前会话已停止业务处理，AI结果不再开放")
    audit(session, who, "processing.result_read", result.id)
    session.commit()
    return result_view(session, result)


@router.get("/processing/results")
def results(
    request: Request,
    session: DB,
    message_id: str,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    who = principal(request, session)
    message = scoped(session, Message, message_id, who)
    query = select(ProcessingResult).where(
        ProcessingResult.workspace_id == who.workspace_id, ProcessingResult.message_id == message_id
    )
    if (
        scoped(session, Conversation, message.conversation_id, who).privacy_scope
        != "business_approved"
    ):
        query = query.where(ProcessingResult.kind.in_(["ocr", "asr"]))
    if cursor:
        scoped(session, ProcessingResult, cursor, who)
        query = query.where(ProcessingResult.id > cursor)
    rows = list(session.scalars(query.order_by(ProcessingResult.id).limit(limit + 1)))
    return page(rows, limit, lambda row: result_view(session, row))


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_processing(job_id: str, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    job = scoped(session, Job, job_id, who)
    session.refresh(job, with_for_update=True)
    if job.kind == "model_install":
        if job.status not in {"queued", "running", "completed"}:
            job.status, job.failure_code, job.lease_token = "queued", None, None
            job.attempt_count, job.next_retry_at = 0, None
            audit(session, who, "model.install_retry", job.id)
            session.commit()
        return {"job_id": job.id, "status": job.status}
    if job.kind not in processing.KINDS:
        raise ApiError(409, "USE_IMPORT_RETRY", "请从导入批次重试该任务")
    if not processing.enabled(session, request.app.state.settings, who.workspace_id, job.kind):
        raise ApiError(409, "MODULE_DISABLED", "请先启用对应模块")
    if job.status in {"cancelled", "failed_permanent", "failed_retryable", "dead_letter"}:
        job.status, job.lease_token, job.failure_code = "queued", None, None
        job.attempt_count, job.next_retry_at = 0, None
        audit(session, who, "processing.retry", job.id)
        session.commit()
    return {"job_id": job.id, "status": job.status}
