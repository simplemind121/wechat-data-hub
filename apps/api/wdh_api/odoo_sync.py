"""Approved, durable draft delivery through the idempotent wdh_bridge Odoo addon."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from wdh_domain.models import (
    Conversation,
    EntityAssertion,
    Job,
    Membership,
    Message,
    OdooDelivery,
    User,
    Workspace,
)

from wdh_api.config import Settings
from wdh_api.entities import verified_payload
from wdh_api.ingest import fingerprint
from wdh_api.routes import DB, scoped
from wdh_api.security import ApiError, Principal, audit, principal

router = APIRouter(prefix="/api/v1/integrations/odoo", tags=["integrations"])


def instance_hash(config: Settings) -> str:
    return fingerprint([config.odoo_url.rstrip("/"), config.odoo_database])


class Rpc:
    def __init__(self, config: Settings, transport: httpx.BaseTransport | None = None):
        from wdh_api.odoo import configured

        if not config.enable_odoo or not configured(config):
            raise ValueError("ODOO_NOT_CONFIGURED")
        parts = urlsplit(config.odoo_url)
        if parts.scheme != "https" and not (
            parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "odoo"}
        ):
            raise ValueError("ODOO_REQUIRES_HTTPS")
        if (
            not parts.hostname
            or parts.username
            or parts.password
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
        ):
            raise ValueError("ODOO_INVALID_URL")
        self.config, self.uid, self.counter = config, 0, 0
        self.client = httpx.Client(
            transport=transport, timeout=15, follow_redirects=False, trust_env=False
        )

    def close(self) -> None:
        self.client.close()

    def rpc(self, service: str, method: str, args: list[Any]) -> Any:
        self.counter += 1
        with self.client.stream(
            "POST",
            self.config.odoo_url.rstrip("/") + "/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "id": self.counter,
                "params": {"service": service, "method": method, "args": args},
            },
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for piece in response.iter_bytes():
                data.extend(piece)
                if len(data) > 2_097_152:
                    raise ValueError("ODOO_RESPONSE_LIMIT")
        result = json.loads(data)
        if (
            not isinstance(result, dict)
            or result.get("id") != self.counter
            or "error" in result
            or "result" not in result
        ):
            raise ValueError("ODOO_RPC_REJECTED")
        return result["result"]

    def execute(
        self, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None
    ) -> Any:
        key = self.config.odoo_api_key.get_secret_value() if self.config.odoo_api_key else ""
        if not self.uid:
            self.uid = self.rpc(
                "common",
                "authenticate",
                [self.config.odoo_database, self.config.odoo_username, key, {}],
            )
            if type(self.uid) is not int or self.uid <= 0:
                raise ValueError("ODOO_AUTHENTICATION_FAILED")
        return self.rpc(
            "object",
            "execute_kw",
            [self.config.odoo_database, self.uid, key, model, method, args, kwargs or {}],
        )


class Mapping(BaseModel):
    existing_id: int | None = Field(default=None, gt=0)
    partner_id: int | None = Field(default=None, gt=0)
    product_id: int | None = Field(default=None, gt=0)
    currency_id: int | None = Field(default=None, gt=0)
    uom_id: int | None = Field(default=None, gt=0)
    quantity: Decimal | None = Field(
        default=None, gt=0, le=1_000_000_000, max_digits=18, decimal_places=6
    )


class PlanRequest(BaseModel):
    entity_id: str
    target_model: Literal[
        "res.partner", "product.template", "purchase.order", "sale.order", "crm.lead"
    ]
    mapping: Mapping = Field(default_factory=Mapping)


class SyncRequest(PlanRequest):
    confirm: Literal[True]


def plan(data: PlanRequest, who: Principal, session: Any) -> tuple[EntityAssertion, dict[str, Any]]:
    entity = scoped(session, EntityAssertion, data.entity_id, who)
    if entity.review_status != "approved" or not entity.approved_payload:
        raise ApiError(409, "APPROVAL_REQUIRED", "仅已批准的业务信息可以同步")
    payload = verified_payload(session, who, entity)
    allowed = {
        "customer": {"res.partner", "crm.lead"},
        "supplier": {"res.partner"},
        "product": {"product.template"},
        "quotation": {"purchase.order", "sale.order"},
        "purchase_intent": {"purchase.order"},
        "order_candidate": {"sale.order", "crm.lead"},
    }
    if data.target_model not in allowed.get(entity.entity_type, set()):
        raise ApiError(422, "ODOO_MAPPING_UNSUPPORTED", "该业务类型不能映射到所选模型")
    name = payload.get("name") or payload.get("company_name") or payload.get("product_model")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(422, "ODOO_NAME_REQUIRED", "缺少有来源证据的名称或型号")
    values: dict[str, Any]
    if data.target_model in {"res.partner", "product.template", "crm.lead"}:
        if data.mapping.existing_id and data.target_model in {"res.partner", "product.template"}:
            values = {"wdh_existing_id": data.mapping.existing_id}
        else:
            values = {"name": name}
        if (
            "name" in values
            and data.target_model == "product.template"
            and payload.get("product_model")
        ):
            values["default_code"] = payload["product_model"]
    else:
        mapping = data.mapping
        if not all(
            [
                mapping.partner_id,
                mapping.product_id,
                mapping.currency_id,
                mapping.uom_id,
                mapping.quantity,
            ]
        ):
            raise ApiError(
                422,
                "ODOO_MAPPING_REQUIRED",
                "请选择已核对的客户或供应商、产品、币种、单位，并填写本次草稿数量",
            )
        try:
            price = Decimal(str(payload["unit_price"]))
        except Exception as exc:
            raise ApiError(422, "ODOO_PRICE_REQUIRED", "草稿需要来源中的明确单价") from exc
        if (
            not price.is_finite()
            or price <= 0
            or price > Decimal("1000000000000")
            or not payload.get("currency")
        ):
            raise ApiError(422, "ODOO_PRICE_REQUIRED", "价格或币种需核对")
        line = {
            "product_id": mapping.product_id,
            "name": name,
            "product_uom_qty" if data.target_model == "sale.order" else "product_qty": float(
                mapping.quantity or 0
            ),
            "price_unit": float(price),
            "product_uom_id": mapping.uom_id,
        }
        values = {
            "partner_id": mapping.partner_id,
            "currency_id": mapping.currency_id,
            "order_line": [[0, 0, line]],
        }
    return entity, values


@router.post("/plan")
def preview(data: PlanRequest, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    _, values = plan(data, who, session)
    return {
        "dry_run": True,
        "remote_writes": False,
        "target_model": data.target_model,
        "values": values,
        "quantity_source": "administrator_selected_draft_quantity",
        "requires_bridge": "wdh_bridge",
    }


@router.post("/sync", status_code=202)
def enqueue(data: SyncRequest, request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "admin")
    config = request.app.state.settings
    if not config.enable_odoo or not config.enable_odoo_writes:
        raise ApiError(409, "ODOO_WRITES_DISABLED", "请先配置测试实例及启用草稿投递")
    entity, values = plan(data, who, session)
    session.scalar(select(Workspace).where(Workspace.id == who.workspace_id).with_for_update())
    # One external creation per approved entity and model; a changed mapping requires review,
    # never a new implicit idempotency key that could create a second remote order.
    key = fingerprint(
        [who.workspace_id, entity.id, instance_hash(config), data.target_model, "bridge-v1"]
    )
    existing = session.scalar(
        select(OdooDelivery).where(
            OdooDelivery.workspace_id == who.workspace_id, OdooDelivery.idempotency_key == key
        )
    )
    evidence_hash = fingerprint([entity.approved_payload, entity.evidence])
    if existing:
        if existing.values != values or existing.evidence_hash != evidence_hash:
            raise ApiError(409, "ODOO_PLAN_CHANGED", "该实体已有投递记录，请先核对原草稿和映射")
        return {"delivery_id": existing.id, "job_id": existing.job_id, "status": "already_queued"}
    job = Job(
        workspace_id=who.workspace_id,
        kind="odoo_sync",
        idempotency_key=key,
        payload={"actor_id": who.user_id},
    )
    session.add(job)
    session.flush()
    delivery = OdooDelivery(
        workspace_id=who.workspace_id,
        entity_id=entity.id,
        job_id=job.id,
        idempotency_key=key,
        instance_hash=instance_hash(config),
        target_model=data.target_model,
        values=values,
        evidence_hash=evidence_hash,
    )
    session.add(delivery)
    session.flush()
    audit(session, who, "odoo.queued", delivery.id, target_model=data.target_model)
    session.commit()
    return {"delivery_id": delivery.id, "job_id": job.id, "status": "queued"}


@router.get("/outbox")
def outbox(request: Request, session: DB) -> dict[str, Any]:
    who = principal(request, session, "reviewer")
    rows = session.execute(
        select(OdooDelivery, Job)
        .join(Job, Job.id == OdooDelivery.job_id)
        .where(OdooDelivery.workspace_id == who.workspace_id)
        .order_by(OdooDelivery.created_at.desc())
        .limit(100)
    )
    return {
        "items": [
            {
                "id": row.id,
                "entity_id": row.entity_id,
                "target_model": row.target_model,
                "remote_id": row.remote_id,
                "read_back": row.read_back,
                "status": job.status,
                "failure_code": job.failure_code,
                "job_id": job.id,
                "attempts": job.attempt_count,
            }
            for row, job in rows
        ]
    }


@router.post("/outbox/{delivery_id}/retry")
def retry(delivery_id: str, request: Request, session: DB) -> dict[str, str]:
    who = principal(request, session, "admin")
    row = scoped(session, OdooDelivery, delivery_id, who)
    job = session.get(Job, row.job_id)
    if not job or job.status not in {
        "failed_permanent",
        "dead_letter",
        "failed_retryable",
        "cancelled",
    }:
        raise ApiError(409, "ODOO_RETRY_UNAVAILABLE", "此任务暂不需要重试")
    job.status, job.failure_code, job.attempt_count = "queued", None, 0
    job.next_retry_at, job.lease_token, job.lease_until = None, None, None
    audit(session, who, "odoo.retry_approved", row.id)
    session.commit()
    return {"status": "queued"}


@router.get("/lookup")
def lookup(
    request: Request,
    session: DB,
    model: Literal["res.partner", "product.template", "product.product", "res.currency", "uom.uom"],
    q: str = "",
) -> dict[str, Any]:
    principal(request, session, "admin")
    if len(q) > 100:
        raise ApiError(422, "INVALID_QUERY", "查询内容过长")
    rpc = Rpc(request.app.state.settings)
    try:
        rows = rpc.execute(
            model,
            "search_read",
            [[["name", "ilike", q]]],
            {"fields": ["id", "display_name"], "limit": 20},
        )
        return {"items": rows}
    finally:
        rpc.close()


def deliver(
    worker: Any, job_id: str, token: str, transport: httpx.BaseTransport | None = None
) -> None:
    config = worker.settings
    if not config.enable_odoo or not config.enable_odoo_writes:
        raise ValueError("ODOO_WRITES_DISABLED")
    # Hold row/workspace locks through the bounded RPC so permission revocation and local
    # concurrent workers cannot race a draft dispatch. Remote uniqueness survives process death.
    with worker.factory.begin() as session:
        job = worker.owned_job(session, job_id, token)
        session.scalar(select(Workspace).where(Workspace.id == job.workspace_id).with_for_update())
        row = session.scalar(
            select(OdooDelivery).where(OdooDelivery.job_id == job.id).with_for_update()
        )
        if not row or row.instance_hash != instance_hash(config):
            raise ValueError("ODOO_INSTANCE_CHANGED")
        actor = session.get(User, job.payload.get("actor_id"))
        member = session.scalar(
            select(Membership).where(
                Membership.user_id == job.payload.get("actor_id"),
                Membership.workspace_id == job.workspace_id,
                Membership.role == "admin",
            )
        )
        if not actor or not actor.is_active or not member:
            raise ValueError("ODOO_APPROVER_REVOKED")
        who = Principal(actor.id, job.workspace_id, "admin", actor.username)
        entity = session.scalar(
            select(EntityAssertion).where(EntityAssertion.id == row.entity_id).with_for_update()
        )
        if (
            not entity
            or entity.review_status != "approved"
            or fingerprint([entity.approved_payload, entity.evidence]) != row.evidence_hash
        ):
            raise ValueError("ODOO_EVIDENCE_CHANGED")
        for item in entity.evidence:
            session.scalar(
                select(Conversation)
                .join(Message, Message.conversation_id == Conversation.id)
                .where(
                    Message.id == item["message_id"], Conversation.workspace_id == who.workspace_id
                )
                .with_for_update(of=Conversation)
            )
        payload = verified_payload(session, who, entity)
        rpc = Rpc(config, transport)
        try:
            if row.target_model in {"purchase.order", "sale.order"}:
                currencies = rpc.execute(
                    "res.currency", "read", [[row.values["currency_id"]]], {"fields": ["name"]}
                )
                if (
                    not isinstance(currencies, list)
                    or len(currencies) != 1
                    or currencies[0].get("name") != payload.get("currency")
                ):
                    raise ValueError("ODOO_CURRENCY_MISMATCH")
            result = rpc.execute(
                "wdh.sync.request",
                "apply_approved",
                [row.idempotency_key, row.target_model, row.values],
            )
            if (
                not isinstance(result, dict)
                or type(result.get("remote_id")) is not int
                or result["remote_id"] <= 0
                or result.get("model") != row.target_model
            ):
                raise ValueError("ODOO_INVALID_RECEIPT")
            fields = (
                ["id", "name", "state", "partner_id", "currency_id", "order_line"]
                if row.target_model in {"purchase.order", "sale.order"}
                else ["id", "name"]
            )
            records = rpc.execute(
                row.target_model, "read", [[result["remote_id"]]], {"fields": fields}
            )
            if (
                not isinstance(records, list)
                or len(records) != 1
                or records[0].get("id") != result["remote_id"]
            ):
                raise ValueError("ODOO_READ_BACK_FAILED")
            if "state" in fields and records[0].get("state") != "draft":
                raise ValueError("ODOO_REMOTE_NOT_DRAFT")
            if "state" in fields:
                remote = records[0]
                for field in ("partner_id", "currency_id"):
                    value = remote.get(field)
                    if not isinstance(value, list) or not value or value[0] != row.values[field]:
                        raise ValueError("ODOO_READ_BACK_MISMATCH")
                lines = rpc.execute(
                    "purchase.order.line"
                    if row.target_model == "purchase.order"
                    else "sale.order.line",
                    "read",
                    [remote.get("order_line", [])],
                    {
                        "fields": [
                            "product_id",
                            "price_unit",
                            "product_uom_id",
                            "product_qty"
                            if row.target_model == "purchase.order"
                            else "product_uom_qty",
                        ]
                    },
                )
                expected = row.values["order_line"][0][2]
                if not isinstance(lines, list) or len(lines) != 1:
                    raise ValueError("ODOO_READ_BACK_MISMATCH")
                for field in ("product_id", "product_uom_id"):
                    if (
                        not isinstance(lines[0].get(field), list)
                        or lines[0][field][0] != expected[field]
                    ):
                        raise ValueError("ODOO_READ_BACK_MISMATCH")
                for field in (
                    "price_unit",
                    "product_qty" if row.target_model == "purchase.order" else "product_uom_qty",
                ):
                    actual = Decimal(str(lines[0].get(field)))
                    if not actual.is_finite() or abs(
                        actual - Decimal(str(expected[field]))
                    ) > Decimal("0.000001"):
                        raise ValueError("ODOO_READ_BACK_MISMATCH")
                remote["verified_lines"] = lines
            row.remote_id, row.read_back = result["remote_id"], records[0]
            job.status, job.failure_code, job.lease_until = "completed", None, None
            job.updated_at = datetime.now(UTC)
            audit(
                session,
                who,
                "odoo.draft_verified",
                row.id,
                target_model=row.target_model,
                remote_id=row.remote_id,
            )
        finally:
            rpc.close()
