"""Tests require a dedicated empty database. No downgrade or destructive cleanup is performed."""

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from wdh_api.config import get_settings
from wdh_domain.models import Account, Base, Device, IngestBatch, RawRecord, SourceBlob, Workspace

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not configured; SQLite is not PostgreSQL evidence")
    result = create_engine(url)
    assert result.dialect.name == "postgresql"
    assert not inspect(result).get_table_names(), "Use a new empty disposable test database"
    with patch.dict(os.environ, {"DATABASE_URL": url}):
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        command.upgrade(Config("alembic.ini"), "head")
        command.check(Config("alembic.ini"))
        get_settings.cache_clear()
    yield result
    result.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection, connection.begin():
        with Session(connection, join_transaction_mode="create_savepoint") as result:
            yield result


def seed(session: Session) -> tuple[Workspace, Account, Device, SourceBlob, IngestBatch]:
    workspace = Workspace(name="synthetic workspace")
    session.add(workspace)
    session.flush()
    account = Account(workspace_id=workspace.id, account_ref="synthetic-a")
    session.add(account)
    session.flush()
    device = Device(
        workspace_id=workspace.id,
        account_id=account.id,
        device_ref="synthetic-device",
        platform="ios",
    )
    blob = SourceBlob(
        workspace_id=workspace.id, sha256="a" * 64, byte_size=3, cas_key="sha256/aa/" + "a" * 64
    )
    session.add_all([device, blob])
    session.flush()
    batch = IngestBatch(
        workspace_id=workspace.id,
        account_id=account.id,
        device_id=device.id,
        main_blob_id=blob.id,
        adapter_id="synthetic",
        adapter_version="1.0.0",
        manifest={"consent_scope": "synthetic-data-only"},
    )
    session.add(batch)
    session.flush()
    return workspace, account, device, blob, batch


def test_migration_matches_models_on_postgres17(engine: Engine) -> None:
    with engine.connect() as connection:
        assert str(connection.exec_driver_sql("SHOW server_version").scalar()).startswith("17.")
    assert set(inspect(engine).get_table_names()) == {*Base.metadata.tables, "alembic_version"}


def test_cross_workspace_reference_rejected(session: Session) -> None:
    _, account, _, _, _ = seed(session)
    other = Workspace(name="synthetic other")
    session.add(other)
    session.flush()
    session.add(
        Device(workspace_id=other.id, account_id=account.id, device_ref="foreign", platform="macos")
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_batch_cannot_mix_accounts_on_one_workspace(session: Session) -> None:
    workspace, _, device, blob, _ = seed(session)
    other = Account(workspace_id=workspace.id, account_ref="synthetic-other")
    session.add(other)
    session.flush()
    session.add(
        IngestBatch(
            workspace_id=workspace.id,
            account_id=other.id,
            device_id=device.id,
            main_blob_id=blob.id,
            adapter_id="new",
            adapter_version="1",
            manifest={},
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_batch_key_rejected(session: Session) -> None:
    workspace, account, device, blob, _ = seed(session)
    session.add(
        IngestBatch(
            workspace_id=workspace.id,
            account_id=account.id,
            device_id=device.id,
            main_blob_id=blob.id,
            adapter_id="synthetic",
            adapter_version="1.0.0",
            manifest={},
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_raw_locator_unique_but_identical_bytes_remain_distinct(session: Session) -> None:
    workspace, _, _, _, batch = seed(session)
    for locator in ("messages.jsonl:1", "messages.jsonl:2"):
        session.add(
            RawRecord(
                workspace_id=workspace.id,
                batch_id=batch.id,
                source_record_locator=locator,
                raw_sha256="b" * 64,
            )
        )
    session.flush()
    session.add(
        RawRecord(
            workspace_id=workspace.id,
            batch_id=batch.id,
            source_record_locator="messages.jsonl:1",
            raw_sha256="b" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_foreign_batch_raw_record_rejected(session: Session) -> None:
    _, _, _, _, batch = seed(session)
    other = Workspace(name="synthetic other")
    session.add(other)
    session.flush()
    session.add(
        RawRecord(
            workspace_id=other.id,
            batch_id=batch.id,
            source_record_locator="messages.jsonl:1",
            raw_sha256="b" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
