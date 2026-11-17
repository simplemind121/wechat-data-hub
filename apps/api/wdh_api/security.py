import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from wdh_domain.models import AuditEvent, LoginSession, Membership, User


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"wdh-csrf-v1", hashlib.sha256).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt-v1${salt}${hashed.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$")
        return hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    role: str
    username: str


def principal(request: Request, session: Session, minimum: str = "reader") -> Principal:
    token = request.cookies.get("wdh_session", "")
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "请先登录")
    current = session.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
    if not token or not current or as_utc(current.expires_at) <= datetime.now(UTC):
        raise ApiError(401, "UNAUTHENTICATED", "请先登录")
    user = session.get(User, current.user_id)
    member = session.scalar(
        select(Membership).where(
            Membership.user_id == current.user_id, Membership.workspace_id == current.workspace_id
        )
    )
    if not user or not user.is_active or not member:
        raise ApiError(401, "SESSION_INVALID", "登录已失效")
    if {"reader": 0, "reviewer": 1, "admin": 2}[member.role] < {
        "reader": 0,
        "reviewer": 1,
        "admin": 2,
    }[minimum]:
        raise ApiError(403, "FORBIDDEN", "当前角色无权执行此操作")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_token(token)):
            raise ApiError(403, "CSRF_REJECTED", "请刷新页面后重试")
    return Principal(user.id, current.workspace_id, member.role, user.username)


def audit(
    session: Session, who: Principal, event: str, object_id: str | None = None, **details: Any
) -> None:
    session.add(
        AuditEvent(
            workspace_id=who.workspace_id,
            actor_id=who.user_id,
            event_type=event,
            object_id=object_id,
            details=details,
        )
    )
