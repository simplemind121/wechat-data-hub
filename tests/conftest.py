import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from wdh_api.config import Settings, get_settings
from wdh_api.main import create_app
from wdh_api.worker import Worker


@pytest.fixture
def product(tmp_path: Path):
    url = f"sqlite+pysqlite:///{tmp_path}/product.db"
    postgres = os.getenv("PRODUCT_POSTGRES_URL")
    namespace_engine, namespace = None, None
    if postgres:
        namespace_engine = create_engine(postgres, isolation_level="AUTOCOMMIT")
        namespace = "wdhtest_" + uuid4().hex
        with namespace_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{namespace}"')
        url = make_url(postgres).set(database=namespace).render_as_string(hide_password=False)
    with patch.dict(os.environ, {"DATABASE_URL": url}):
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        get_settings.cache_clear()
    settings = Settings(_env_file=None, database_url=url, data_root=tmp_path / "archive")
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app, Worker(settings, app.state.factory)
    if namespace_engine is not None:
        with namespace_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{namespace}"')
        namespace_engine.dispose()


@pytest.fixture
def restore_target(tmp_path: Path):
    url = f"sqlite+pysqlite:///{tmp_path}/restored.db"
    controller, name = None, None
    if postgres := os.getenv("PRODUCT_POSTGRES_URL"):
        controller = create_engine(postgres, isolation_level="AUTOCOMMIT")
        name = "wdhrestore_" + uuid4().hex
        with controller.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
        url = make_url(postgres).set(database=name).render_as_string(hide_password=False)
    yield Settings(_env_file=None, database_url=url, data_root=tmp_path / "restored-cas")
    if controller is not None:
        with controller.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        controller.dispose()
