import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from wdh_api.backup import create_backup, restore_backup
from wdh_api.config import Settings
from wdh_api.demo import demo_zip
from wdh_api.main import create_app

from tests.integration.test_formats import media_bundle
from tests.integration.test_product import initialize, upload


def test_encrypted_restore_into_clean_environment_preserves_records_hashes_and_login(
    product, tmp_path: Path, restore_target
) -> None:
    client, app, worker = product
    initialize(client)
    media_data, media_bytes = media_bundle()
    upload(client, media_data)
    worker.run_once()
    original = client.get("/api/v1/overview").json()
    path = tmp_path / "backup.wdhbak"
    start = time.perf_counter()
    result = create_backup(app.state.engine, worker.store, path, "synthetic-backup-passphrase")
    backup_seconds = time.perf_counter() - start
    assert path.stat().st_mode & 0o777 == 0o600
    assert b"M620" not in path.read_bytes()
    target = restore_target
    start = time.perf_counter()
    restored = restore_backup(path, "synthetic-backup-passphrase", target)
    restore_seconds = time.perf_counter() - start
    assert restored["source_counts"] == result["counts"]
    assert restored["counts"]["login_sessions"] == 0
    assert all(
        restored["counts"][key] == value
        for key, value in result["counts"].items()
        if key != "login_sessions"
    )
    assert restored["objects"] == result["objects"]
    with TestClient(create_app(target)) as recovered:
        recovered.cookies.set("wdh_session", client.cookies.get("wdh_session"))
        assert recovered.get("/api/v1/me").status_code == 401
        login = recovered.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "synthetic-test-password"}
        )
        assert login.status_code == 200
        assert recovered.get("/api/v1/overview").json()["messages"] == original["messages"]
        assert recovered.get("/api/v1/search?q=M620").json()["items"]
        messages = recovered.get("/api/v1/search").json()["items"]
        detail = recovered.get("/api/v1/messages/" + messages[0]["id"]).json()
        assert detail["observations"][0]["raw"]["raw_sha256"]
        media = next(row for row in messages if row["attachments"])["attachments"][0]
        downloaded = recovered.get(f"/api/v1/attachments/{media['id']}/download")
        assert downloaded.content == media_bytes
    if app.state.engine.dialect.name == "postgresql" and target.database_url.startswith(
        "postgresql"
    ):
        Path("docs/evidence/restore-drill.json").write_text(
            json.dumps(
                {
                    "source_database": "PostgreSQL 17",
                    "restored_database": "new PostgreSQL 17 database",
                    "scope": "synthetic-only",
                    "backup_seconds": backup_seconds,
                    "restore_seconds": restore_seconds,
                    "rpo_seconds": None,
                    "rpo_note": "Consistent snapshot verified; no production schedule is claimed.",
                    "counts": restored["counts"],
                    "source_counts": restored["source_counts"],
                    "objects_hash_verified": restored["objects"],
                    "old_sessions_rejected": True,
                    "restored_media_download_verified": True,
                    "login_search_provenance_verified": True,
                },
                indent=2,
            )
            + "\n"
        )


@pytest.mark.parametrize("damage", ["password", "tamper", "truncate"])
def test_wrong_password_and_modified_backup_rejected_before_database_write(
    product, tmp_path: Path, damage: str
) -> None:
    client, app, worker = product
    initialize(client)
    upload(client, demo_zip())
    worker.run_once()
    path = tmp_path / "source.wdhbak"
    create_backup(app.state.engine, worker.store, path, "synthetic-backup-passphrase")
    data = bytearray(path.read_bytes())
    if damage == "tamper":
        data[100] ^= 1
    elif damage == "truncate":
        data = data[:-10]
    bad = tmp_path / "bad.wdhbak"
    bad.write_bytes(data)
    target = Settings(
        _env_file=None,
        database_url=f"sqlite+pysqlite:///{tmp_path}/empty.db",
        data_root=tmp_path / "new-cas",
    )
    with pytest.raises(ValueError):
        restore_backup(
            bad,
            "wrong-synthetic-password" if damage == "password" else "synthetic-backup-passphrase",
            target,
        )
    from sqlalchemy import inspect
    from wdh_api.db import make_engine

    engine = make_engine(target)
    assert inspect(engine).get_table_names() == []
    engine.dispose()


def test_restore_never_clears_existing_database_or_overwrites_originals(
    product, tmp_path: Path
) -> None:
    client, app, worker = product
    initialize(client)
    upload(client, demo_zip())
    worker.run_once()
    backup = tmp_path / "backup.wdhbak"
    create_backup(app.state.engine, worker.store, backup, "synthetic-backup-passphrase")
    existing_db = Settings(
        _env_file=None, database_url=app.state.settings.database_url, data_root=tmp_path / "new-cas"
    )
    with pytest.raises(ValueError, match="RESTORE_DATABASE_MUST_BE_EMPTY"):
        restore_backup(backup, "synthetic-backup-passphrase", existing_db)
    assert client.get("/api/v1/overview").json()["messages"] == 5


def test_processing_evidence_restores_with_modules_disabled_and_vectors_rebuild(
    product, tmp_path, restore_target
):
    from pathlib import Path

    from tests.integration.test_processing import image_source

    client, app, worker = product
    message, original = image_source(product)
    settings = app.state.settings
    settings.local_model_server = Path(".local/models/runtime/llama-server").resolve()
    settings.embedding_model_file = Path(
        ".local/models/embedding/bge-small-zh-v1.5-q8_0.gguf"
    ).resolve()
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "business_approved"},
    )
    for kind in ("ocr", "embedding"):
        assert (
            client.patch("/api/v1/processing/modules/" + kind, json={"enabled": True}).status_code
            == 200
        )
    result = client.post(
        "/api/v1/process/ocr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()
    worker.run_once()
    ocr = client.get("/api/v1/processing/results/" + result["result_id"]).json()
    client.post(
        "/api/v1/process/embedding",
        json={"message_id": message["id"], "source_result_id": ocr["id"]},
    )
    worker.run_once()
    path = tmp_path / "processing.wdhbak"
    result = create_backup(app.state.engine, worker.store, path, "synthetic-processing-backup")
    restored = restore_backup(path, "synthetic-processing-backup", restore_target)
    assert restored["counts"]["processing_results"] == result["counts"]["processing_results"] == 2
    restore_target.local_model_server = settings.local_model_server
    restore_target.embedding_model_file = settings.embedding_model_file
    with TestClient(create_app(restore_target)) as recovered:
        login = recovered.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "synthetic-test-password"}
        )
        recovered.headers["x-csrf-token"] = login.json()["csrf_token"]
        modules = recovered.get("/api/v1/processing/capabilities").json()["modules"]
        assert not any(module["enabled"] for module in modules.values())
        assert recovered.get("/api/v1/search?q=3200").json()["items"]
        assert (
            recovered.get("/api/v1/processing/results/" + ocr["id"]).json()["text"] == ocr["text"]
        )
        assert (
            recovered.patch(
                "/api/v1/processing/modules/embedding", json={"enabled": True}
            ).status_code
            == 200
        )
        hits = recovered.get("/api/v1/semantic/search?q=M620").json()["items"]
        assert hits and hits[0]["citation"]["source_result_id"] == ocr["id"]
        assert (
            recovered.get(
                "/api/v1/attachments/" + message["attachments"][0]["id"] + "/download"
            ).content
            == original
        )
