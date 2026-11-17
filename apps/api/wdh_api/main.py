import shutil
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.types import Message as ASGIMessage
from wdh_storage.cas import StorageError

from wdh_api.config import Settings, get_settings
from wdh_api.db import make_engine, sessions
from wdh_api.routes import router
from wdh_api.security import ApiError, principal

SCHEMA_REVISION = "0003_entities"


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, maximum: int) -> None:
        self.app, self.maximum = app, maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        total = 0
        limit = self.maximum + 2_097_152 if scope["path"] == "/api/v1/imports" else 1_048_576

        async def limited_receive() -> ASGIMessage:
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise ApiError(413, "SIZE_LIMIT", "请求内容超过限制")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    engine = make_engine(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        from wdh_storage.cas import ContentStore

        ContentStore(config.data_root, config.import_max_bytes)
        for name in ("quarantine", "exports"):
            ContentStore._directory(config.data_root.absolute() / name)
        yield
        engine.dispose()

    app = FastAPI(title="WeChat Data Hub", version="0.2.0", lifespan=lifespan)
    app.state.settings = config
    app.state.factory = sessions(engine)
    app.state.engine = engine
    app.add_middleware(BodyLimitMiddleware, maximum=config.import_max_bytes)

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[..., Any]) -> Response:
        # Never trust caller-supplied request IDs; do not log body, credentials or source paths.
        request.state.request_id = str(uuid4())
        try:
            allowed = {host.strip() for host in config.allowed_hosts.split(",")}
            if request.url.hostname not in allowed:
                raise ApiError(400, "INVALID_HOST", "不允许的访问地址")
            origin = request.headers.get("origin")
            if origin and (
                urlparse(origin).hostname not in allowed
                or urlparse(origin).scheme not in {"http", "https"}
            ):
                raise ApiError(403, "ORIGIN_REJECTED", "请从本地工作台访问")
            length = request.headers.get("content-length")
            limit = (
                config.import_max_bytes + 2_097_152
                if request.url.path == "/api/v1/imports"
                else 1_048_576
            )
            if length and (not length.isdecimal() or int(length) > limit):
                raise ApiError(413, "SIZE_LIMIT", "请求内容超过限制")
            public = {
                "/api/v1/auth/status",
                "/api/v1/auth/setup",
                "/api/v1/auth/login",
                "/api/v1/health/live",
                "/api/v1/health/ready",
            }
            if request.url.path.startswith("/api/v1/") and request.url.path not in public:
                with app.state.factory() as session:
                    minimum = (
                        "admin"
                        if request.method == "POST"
                        and request.url.path
                        in {"/api/v1/imports", "/api/v1/users", "/api/v1/backups"}
                        else "reader"
                    )
                    principal(request, session, minimum)
            if request.method == "POST" and request.url.path == "/api/v1/imports" and length:
                free = shutil.disk_usage(config.data_root).free
                if int(length) * 3 + 33_554_432 > free:
                    raise ApiError(
                        507, "INSUFFICIENT_STORAGE", "可用存储空间不足，请释放空间或扩容后导入"
                    )
            response: Response = await call_next(request)
        except ApiError as exc:
            response = error(request, exc.status, exc.code, exc.message)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", str(uuid4())),
                "details": {},
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(
            request,
            exc.status_code,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Resource unavailable",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return error(request, 422, "INVALID_REQUEST", "Request validation failed")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _: Exception) -> JSONResponse:
        return error(request, 500, "INTERNAL_ERROR", "Request could not be completed")

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error(request, exc.status, exc.code, exc.message)

    @app.exception_handler(ValidationError)
    async def source_error(request: Request, _: ValidationError) -> JSONResponse:
        return error(
            request,
            400,
            "INVALID_MANIFEST",
            "导入清单不符合格式，请检查必填字段、时区和文件校验信息",
        )

    @app.exception_handler(ValueError)
    async def value_error(request: Request, _: ValueError) -> JSONResponse:
        return error(request, 400, "INVALID_SOURCE", "导出文件格式或路径不符合要求")

    @app.exception_handler(StorageError)
    async def storage_error(request: Request, _: StorageError) -> JSONResponse:
        return error(request, 400, "STORAGE_REJECTED", "文件超过限制、路径不安全或原件校验失败")

    @app.get("/api/v1/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready", tags=["health"], responses={503: {"description": "Not ready"}})
    def ready(request: Request) -> Response:
        try:
            with engine.connect() as connection:
                revision = connection.execute(text("SELECT version_num FROM alembic_version"))
                if revision.scalar_one() != SCHEMA_REVISION:
                    return error(request, 503, "NOT_READY", "Dependencies not ready")
        except SQLAlchemyError:
            return error(request, 503, "NOT_READY", "Dependencies not ready")
        return JSONResponse({"status": "ready"})

    app.include_router(router)
    return app
