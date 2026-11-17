from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from wdh_api.config import Settings
from wdh_api.main import create_app


def test_live_does_not_require_database_or_external_modules(tmp_path: Path) -> None:
    config = Settings(_env_file=None, database_url=f"sqlite+pysqlite:///{tmp_path}/absent.db")
    with TestClient(create_app(config)) as client:
        response = client.get("/api/v1/health/live")
        assert response.json() == {"status": "ok"}
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert not any(
            (
                config.enable_ocr,
                config.enable_asr,
                config.enable_llm,
                config.enable_odoo,
                config.allow_external_ai,
            )
        )
        ready = client.get("/api/v1/health/ready")
        assert ready.status_code == 503
        assert ready.json()["code"] == "NOT_READY"
        assert str(tmp_path) not in ready.text


def test_ready_requires_migration(tmp_path: Path) -> None:
    import os
    from unittest.mock import patch

    url = f"sqlite+pysqlite:///{tmp_path}/ready.db"
    from wdh_api.config import get_settings

    get_settings.cache_clear()
    with patch.dict(os.environ, {"DATABASE_URL": url}):
        command.upgrade(Config("alembic.ini"), "head")
    get_settings.cache_clear()
    with TestClient(create_app(Settings(_env_file=None, database_url=url))) as client:
        assert client.get("/api/v1/health/ready").json() == {"status": "ready"}


def test_data_routes_require_authentication() -> None:
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/v1/imports")
        assert response.status_code == 401
        assert set(response.json()) == {"code", "message", "request_id", "details"}
        assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_health_contract_matches_checked_in_artifact() -> None:
    import json

    artifact = json.loads(Path("contracts/implemented-openapi.json").read_text())
    assert create_app(Settings(_env_file=None)).openapi() == artifact
