import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from wdh_api.demo import demo_zip
from wdh_domain.models import Job, Message, Observation, RawRecord


def initialize(client: TestClient) -> dict[str, str]:
    result = client.post(
        "/api/v1/auth/setup",
        json={
            "username": "owner",
            "password": "synthetic-test-password",
            "workspace_name": "合成工作空间",
        },
    )
    assert result.status_code == 201, result.text
    client.headers["x-csrf-token"] = result.json()["csrf_token"]
    return result.json()


def upload(client: TestClient, data: bytes) -> dict[str, str]:
    response = client.post(
        "/api/v1/imports", files={"file": ("synthetic.zip", data, "application/zip")}
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_import_three_times_browse_search_sources_export_and_logout(product) -> None:
    client, app, worker = product
    initialize(client)
    first = upload(client, demo_zip())
    assert client.get(f"/api/v1/jobs/{first['job_id']}").json()["status"] == "queued"
    assert worker.run_once()
    status = client.get(f"/api/v1/jobs/{first['job_id']}").json()
    assert status["status"] == "completed", status
    for _ in range(2):
        repeat = upload(client, demo_zip())
        assert repeat["status"] == "already_ingested"
        assert repeat["import_id"] == first["import_id"]
    with app.state.factory() as session:
        assert session.scalar(select(func.count()).select_from(Message)) == 5
        assert session.scalar(select(func.count()).select_from(Observation)) == 5
        assert session.scalar(select(func.count()).select_from(RawRecord)) == 5
    overview = client.get("/api/v1/overview").json()
    assert overview["messages"] == 5
    assert overview["conversations"] == 2
    result = client.get("/api/v1/search", params={"q": "Ｍ６２０ 报价"}).json()
    assert len(result["items"]) == 1
    detail = client.get("/api/v1/messages/" + result["items"][0]["id"]).json()
    assert detail["observations"][0]["raw"]["raw_payload"]["body_text"]
    assert detail["observations"][0]["batch"]["sha256"]
    assert client.get("/api/v1/exports/messages?format=csv").text.count("收到") == 2
    assert len(client.get("/api/v1/exports/messages?format=jsonl").text.splitlines()) == 5
    coverage = client.get(f"/api/v1/imports/{first['import_id']}/coverage").json()
    assert coverage["records"] == 5
    assert coverage["media"]["missing"] == 1
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/overview").status_code == 401


def test_weak_matches_keep_repeated_messages_and_review_records_audit(product) -> None:
    client, _, worker = product
    initialize(client)
    upload(client, demo_zip())
    worker.run_once()
    reviews = client.get("/api/v1/reviews").json()["items"]
    duplicate = next(item for item in reviews if item["review_type"] == "duplicate")
    assert [message["body_text"] for message in duplicate["messages"]] == ["收到", "收到"]
    assert (
        client.post(
            "/api/v1/reviews/" + duplicate["id"] + "/resolve",
            json={"action": "reject", "reason": "确认是两条独立记录"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/overview").json()["messages"] == 5
    assert any(
        item["event_type"] == "review.reject"
        for item in client.get("/api/v1/audit").json()["items"]
    )


def test_two_devices_strong_match_and_missing_media(product) -> None:
    client, _, worker = product
    initialize(client)
    upload(client, demo_zip("ios"))
    worker.run_once()
    upload(client, demo_zip("macos"))
    worker.run_once()
    result = client.get("/api/v1/search?q=M620").json()["items"]
    assert len(result) == 1
    assert result[0]["observation_count"] == 2
    assert client.get("/api/v1/overview").json()["messages"] == 9
    missing = next(
        item for item in client.get("/api/v1/search").json()["items"] if item["attachments"]
    )
    assert (
        client.get(
            "/api/v1/attachments/" + missing["attachments"][0]["id"] + "/download"
        ).status_code
        == 404
    )


def test_cancel_and_retry_archived_job_is_idempotent(product) -> None:
    client, app, worker = product
    initialize(client)
    first = upload(client, demo_zip())
    assert client.post(f"/api/v1/jobs/{first['job_id']}/cancel").status_code == 200
    assert not worker.run_once()
    assert client.post(f"/api/v1/imports/{first['import_id']}/retry").status_code == 202
    worker.run_once()
    # A process dies after committed chunks; expired lease takeover must replay safely.
    with app.state.factory.begin() as session:
        job = session.get(Job, first["job_id"])
        job.status = "running"
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert worker.run_once()
    assert client.get("/api/v1/overview").json()["messages"] == 5


def test_corrupt_row_quarantine_valid_row_survives_and_source_bytes_preserved(product) -> None:
    client, app, worker = product
    initialize(client)
    with zipfile.ZipFile(io.BytesIO(demo_zip())) as package:
        manifest = json.loads(package.read("manifest.json"))
        payload = b"{broken\n" + package.read("messages.jsonl")
    manifest["payload_files"][0].update(
        size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
    )
    response = client.post(
        "/api/v1/imports",
        data={"manifest": json.dumps(manifest)},
        files={"file": ("messages.jsonl", payload)},
    )
    assert response.status_code == 202, response.text
    worker.run_once()
    coverage = client.get(f"/api/v1/imports/{response.json()['import_id']}/coverage").json()
    assert coverage["schema_statuses"] == {"normalized": 5, "quarantined": 1}
    assert client.get("/api/v1/overview").json()["messages"] == 5
    assert worker.store.read(hashlib.sha256(payload).hexdigest()) == payload
    error = client.get(f"/api/v1/imports/{response.json()['import_id']}/errors").json()
    assert error["items"][0]["errors"] == [{"code": "INVALID_JSON"}]
