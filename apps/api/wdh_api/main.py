from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import Response

from wdh_api.config import Settings, get_settings

SCHEMA_REVISION = "0001_bronze"


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    connect_args = {"connect_timeout": 3} if config.database_url.startswith("postgresql") else {}
    engine = create_engine(config.database_url, connect_args=connect_args, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="WeChat Data Hub", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def headers(request: Request, call_next: Callable[..., Any]) -> Response:
        # Never trust caller-supplied request IDs; do not log body, credentials or source paths.
        request.state.request_id = str(uuid4())
        response: Response = await call_next(request)
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

    return app
