"""Evidence-constrained local rule candidates and review; this is not an LLM provider."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from wdh_domain.models import Contact, Conversation, EntityAssertion, Message

from wdh_api.ingest import fingerprint
from wdh_api.security import ApiError, Principal


def evidence_message(session: Session, who: Principal, message_id: str) -> Message:
    try:
        UUID(message_id)
    except ValueError as exc:
        raise ApiError(404, "NOT_FOUND", "未找到证据消息") from exc
    message = session.get(Message, message_id)
    if not message or message.workspace_id != who.workspace_id:
        raise ApiError(404, "NOT_FOUND", "未找到证据消息")
    conversation = session.get(Conversation, message.conversation_id)
    if (
        not conversation
        or conversation.workspace_id != who.workspace_id
        or conversation.privacy_scope != "business_approved"
    ):
        raise ApiError(403, "PRIVATE_CONVERSATION", "需由管理员先允许该会话进行业务处理")
    return message


def normalize_field(key: str, span: str) -> str:
    if key == "currency":
        currencies = {"元": "CNY", "人民币": "CNY", "CNY": "CNY", "USD": "USD", "美元": "USD"}
        if span not in currencies:
            raise ApiError(400, "UNSUPPORTED_CURRENCY", "币种必须来自明确的原始文字")
        return currencies[span]
    if key in {"unit_price", "quantity_moq"}:
        try:
            number = Decimal(span)
        except InvalidOperation as exc:
            raise ApiError(400, "INVALID_NUMBER", "数量或价格必须是来源中的明确数字") from exc
        if not number.is_finite() or number <= 0:
            raise ApiError(400, "INVALID_NUMBER", "数量或价格必须为正数")
        return str(number)
    return span


def quotation_candidate(
    session: Session, who: Principal, message_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    message = evidence_message(session, who, message_id)
    body = message.body_text or ""
    fields: dict[str, str] = {}
    model = re.search(r"\b([A-Za-z][A-Za-z0-9-]*\d[A-Za-z0-9-]*(?:\s+Ultra)?)\b", body)
    price = re.search(r"(\d+(?:\.\d{1,4})?)\s*(元|人民币|CNY|USD|美元)", body)
    quantity = re.search(r"(\d+)\s*(?:套|件|个).{0,6}?(?:起订|起定|MOQ)", body)
    if model:
        fields["product_model"] = model.group(1)
    if price:
        fields["unit_price"], fields["currency"] = price.group(1), price.group(2)
    if quantity:
        fields["quantity_moq"] = quantity.group(1)
    if not {"product_model", "unit_price", "currency"} <= fields.keys():
        raise ApiError(422, "INSUFFICIENT_EVIDENCE", "未找到明确型号、价格和币种，不能生成报价候选")
    evidence = [
        {"field": key, "message_id": message.id, "source_span": span, "value_raw": span}
        for key, span in fields.items()
    ]
    payload = {key: normalize_field(key, span) for key, span in fields.items()}
    contact = session.get(Contact, message.sender_contact_id) if message.sender_contact_id else None
    if contact and contact.workspace_id == who.workspace_id:
        payload["supplier_ref"] = contact.native_ref
        evidence.append(
            {
                "field": "supplier_ref",
                "message_id": message.id,
                "source_span": contact.native_ref,
                "value_raw": contact.native_ref,
                "source_column": "sender_ref",
            }
        )
    return payload, evidence


def verified_payload(
    session: Session,
    who: Principal,
    entity: EntityAssertion,
    corrections: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = dict(
        entity.approved_payload
        if entity.review_status == "approved" and entity.approved_payload is not None
        else entity.payload
    )
    evidence = {item["field"]: item for item in entity.evidence}
    for key, span in (corrections or {}).items():
        if key not in evidence or key == "supplier_ref":
            raise ApiError(400, "UNSUPPORTED_CORRECTION", "该字段不能直接改写，请使用实际来源证据")
        evidence[key] = {**evidence[key], "source_span": span, "value_raw": span}
        values[key] = normalize_field(key, span)
    for key, value in values.items():
        item = evidence.get(key)
        if not item:
            raise ApiError(400, "EVIDENCE_REQUIRED", "每个业务字段均需来源证据")
        message = evidence_message(session, who, item["message_id"])
        span = item["source_span"]
        if item.get("source_column") == "sender_ref":
            contact = (
                session.get(Contact, message.sender_contact_id)
                if message.sender_contact_id
                else None
            )
            valid = bool(
                contact
                and contact.workspace_id == who.workspace_id
                and contact.native_ref == value == span
            )
        else:
            valid = bool(
                span and span in (message.body_text or "") and normalize_field(key, span) == value
            )
        if not valid:
            raise ApiError(400, "UNSUPPORTED_FIELD_VALUE", "字段值或修改缺乏原始证据")
    if corrections:
        entity.evidence = list(evidence.values())
    return values


def candidate_key(message_id: str, payload: dict[str, Any]) -> str:
    return fingerprint(["local-rules-1.0.0", message_id, payload])
