"""Synthetic collector contracts; no WeChat client login is exercised."""

import io

from tests.integration.test_product import initialize


def source(client, kind="personal_files"):
    response = client.post(
        "/api/v1/sources",
        json={
            "name": "合成测试采集端",
            "kind": kind,
            "metadata": {
                "account_ref": "synthetic-collector",
                "device_ref": "synthetic-device",
                "platform": "macos",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_scoped_collector_archive_retry_pause_and_rotation(product):
    client, _, worker = product
    initialize(client)
    created = source(client)
    token = created["token"]
    headers = {"Authorization": "Bearer " + token}
    client.cookies.clear()
    assert client.get("/api/v1/search", headers=headers).status_code == 401
    assert client.get("/api/v1/collector/status").status_code == 401
    raw = (
        '{"conversation_ref":"群聊","sender_ref":"a",'
        '"sent_at":"2026-11-20T08:00:00+08:00","message_type":"text",'
        '"body_text":"报价 M620 3200元 😀"}\n'
    ).encode()

    def upload(data=raw):
        return client.post(
            "/api/v1/collector/batches",
            headers=headers,
            files={"file": ("messages.jsonl", io.BytesIO(data), "application/octet-stream")},
            data={"cursor": "file-1"},
        )

    first = upload()
    assert first.status_code == 202, first.text
    assert upload().json()["import_id"] == first.json()["import_id"]
    assert upload(raw + b"\n").status_code == 409
    assert worker.run_once()
    assert token not in client.get("/api/v1/collector/status", headers=headers).text
    # Re-login as the source administrator; pausing takes effect on the next request.
    response = client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "synthetic-test-password"}
    )
    client.headers["x-csrf-token"] = response.json()["csrf_token"]
    sid = created["source"]["id"]
    assert client.post(f"/api/v1/sources/{sid}/state", json={"enabled": False}).status_code == 200
    assert client.get("/api/v1/collector/status", headers=headers).status_code == 401
    client.post(f"/api/v1/sources/{sid}/state", json={"enabled": True})
    new = client.post(f"/api/v1/sources/{sid}/rotate").json()["token"]
    assert client.get("/api/v1/collector/status", headers=headers).status_code == 401
    assert (
        client.get(
            "/api/v1/collector/status", headers={"Authorization": "Bearer " + new}
        ).status_code
        == 200
    )


def test_source_admin_csrf_and_bound_metadata(product):
    client, _, _ = product
    initialize(client)
    created = source(client)
    assert client.post("/api/v1/sources", json={}).status_code in {403, 422}
    headers = {"Authorization": "Bearer " + created["token"]}
    assert (
        client.post(
            "/api/v1/collector/heartbeat", headers=headers, json={"failure_code": "包含私密内容"}
        ).status_code
        == 422
    )
    status = client.get("/api/v1/sources").json()
    assert created["token"] not in str(status) and "token_hash" not in str(status)


def test_collector_owner_role_revocation_and_csrf_gate(product):
    from sqlalchemy import select
    from wdh_domain.models import Membership

    client, app, _ = product
    initialize(client)
    created = source(client)
    token = {"Authorization": "Bearer " + created["token"]}
    csrf = client.headers.pop("x-csrf-token")
    assert (
        client.post(
            f"/api/v1/sources/{created['source']['id']}/state", json={"enabled": False}
        ).status_code
        == 403
    )
    client.headers["x-csrf-token"] = csrf
    with app.state.factory.begin() as session:
        session.scalar(select(Membership)).role = "reader"
    assert client.get("/api/v1/sources").status_code == 403
    assert client.get("/api/v1/collector/status", headers=token).status_code == 401


def test_source_credentials_revoked_by_backup_restore(product, restore_target, tmp_path):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from wdh_api.backup import create_backup, restore_backup
    from wdh_api.db import make_engine
    from wdh_domain.models import DataSource
    from wdh_storage.cas import ContentStore

    client, app, _ = product
    initialize(client)
    created = source(client)
    backup = tmp_path / "synthetic-source.wdhbak"
    create_backup(
        app.state.engine,
        ContentStore(app.state.settings.data_root, 10485760),
        backup,
        "synthetic-source-backup-passphrase",
    )
    restore_backup(backup, "synthetic-source-backup-passphrase", restore_target)
    engine = make_engine(restore_target)
    with Session(engine) as session:
        restored = session.scalar(select(DataSource))
        assert restored and restored.id == created["source"]["id"]
        assert not restored.enabled and restored.token_hash is None
    engine.dispose()


def test_wecom_checkpoint_cannot_regress_after_concurrent_archive(product, tmp_path):
    from unittest.mock import patch

    from wdh_api.ingest import accept_upload
    from wdh_api.wecom import archive_page
    from wdh_domain.models import DataSource

    from tests.integration.test_collectors import SDK

    client, app, _ = product
    initialize(client)
    created = source(client, "wecom_archive")
    sdk = SDK()
    bundle, _ = archive_page(sdk, sdk.pull(0), created["source"], {"1": "fixture"}, tmp_path, 0)

    def archive_then_other_collector_advances(*args, **kwargs):
        result = accept_upload(*args, **kwargs)
        with app.state.factory.begin() as session:
            row = session.get(DataSource, created["source"]["id"])
            row.last_cursor = "9"
        return result

    with patch(
        "wdh_api.source_routes.accept_upload", side_effect=archive_then_other_collector_advances
    ):
        response = client.post(
            "/api/v1/collector/batches",
            headers={"Authorization": "Bearer " + created["token"]},
            files={"file": ("pending.zip", bundle.read_bytes())},
            data={"cursor": "1"},
        )
    assert response.status_code == 202, response.text
    headers = {"Authorization": "Bearer " + created["token"]}
    assert client.get("/api/v1/collector/status", headers=headers).json()["last_cursor"] == "9"
