import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from wdh_api.security import password_hash
from wdh_domain.models import Job, Membership, ProcessingResult, User, Workspace

from tests.integration.test_product import initialize, upload


def processing_image_bundle(image: bytes | None = None) -> tuple[bytes, bytes]:
    from wdh_api.demo import demo_zip

    data = image or Path("tests/fixtures/ocr-v1/quotation.png").read_bytes()
    with zipfile.ZipFile(io.BytesIO(demo_zip())) as old:
        manifest = json.loads(old.read("manifest.json"))
        rows = [json.loads(line) for line in old.read("messages.jsonl").splitlines()]
    rows[-1]["message_type"] = "image"
    rows[-1]["body_text"] = "仅合成图片，文字需从图中识别"
    rows[-1]["media"] = [{"path": "media/quotation.png"}]
    payload = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)
    manifest["payload_files"][0].update(
        size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("messages.jsonl", payload)
        archive.writestr("media/quotation.png", data)
    return buffer.getvalue(), data


def image_source(product):
    client, app, worker = product
    initialize(client)
    models = Path(".local/models/tesseract").resolve()
    if models.is_dir():
        app.state.settings.ocr_data_dir = models
    data, original = processing_image_bundle()
    upload(client, data)
    assert worker.run_once()
    message = next(r for r in client.get("/api/v1/search").json()["items"] if r["attachments"])
    return message, original


def test_ocr_off_by_default_then_real_chinese_engine_with_evidence_and_search(product):
    client, app, worker = product
    message, original = image_source(product)
    payload = {"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]}
    assert client.post("/api/v1/process/ocr", json=payload).status_code == 409
    enabled = client.patch("/api/v1/processing/modules/ocr", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    queued = client.post("/api/v1/process/ocr", json=payload)
    assert queued.status_code == 202, queued.text
    assert worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued.json()["result_id"]).json()
    assert result["status"] == "completed", result
    assert "M620" in result["text"] and "3200" in result["text"]
    assert "报价" in result["search_text"]
    assert result["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["details"]["words"]
    assert all(word["bbox"][2] > 0 for word in result["details"]["words"])
    assert result["provider_version"].startswith("tesseract/")
    assert client.get("/api/v1/search?q=3200").json()["items"][-1]["id"] == message["id"]
    repeated = client.post("/api/v1/process/ocr", json=payload).json()
    assert repeated["job_id"] == queued.json()["job_id"]
    with app.state.factory() as session:
        assert session.scalar(select(func.count()).select_from(ProcessingResult)) == 1
    after = client.get("/api/v1/messages/" + message["id"]).json()
    assert after["body_text"] == message["body_text"]
    assert after["processing_results"][0]["id"] == result["id"]
    assert (
        client.get(f"/api/v1/attachments/{payload['attachment_id']}/download").content == original
    )


def test_module_disable_cancels_queued_work_and_preserves_original(product):
    client, _, worker = product
    message, _ = image_source(product)
    client.patch("/api/v1/processing/modules/ocr", json={"enabled": True})
    queued = client.post(
        "/api/v1/process/ocr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()
    assert (
        client.patch("/api/v1/processing/modules/ocr", json={"enabled": False}).status_code == 200
    )
    assert not worker.run_once()
    assert client.get("/api/v1/jobs/" + queued["job_id"]).json()["status"] == "cancelled"
    assert client.get("/api/v1/messages/" + message["id"]).status_code == 200


def test_processing_cancel_has_no_ingest_batch_dependency_and_can_retry(product):
    client, _, worker = product
    message, _ = image_source(product)
    client.patch("/api/v1/processing/modules/ocr", json={"enabled": True})
    job = client.post(
        "/api/v1/process/ocr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()["job_id"]
    assert client.post(f"/api/v1/jobs/{job}/cancel").status_code == 200
    assert client.post(f"/api/v1/jobs/{job}/retry").status_code == 202
    assert worker.run_once()
    assert client.get(f"/api/v1/jobs/{job}").json()["status"] == "completed"


@pytest.mark.parametrize("failure", ["corrupt", "pixels"])
def test_ocr_errors_keep_original_and_never_publish_partial_text(product, failure):
    client, app, worker = product
    message, _ = image_source(product)
    if failure == "corrupt":
        data, _ = processing_image_bundle(b"\x89PNG\r\n\x1a\nsynthetic-corrupt-image")
        upload(client, data)
        worker.run_once()
        message = next(
            row
            for row in client.get("/api/v1/search").json()["items"]
            if any(
                a["sha256"]
                == hashlib.sha256(b"\x89PNG\r\n\x1a\nsynthetic-corrupt-image").hexdigest()
                for a in row["attachments"]
            )
        )
    else:
        app.state.settings.processing_max_pixels = 10
    client.patch("/api/v1/processing/modules/ocr", json={"enabled": True})
    queued = client.post(
        "/api/v1/process/ocr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()
    worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued["result_id"]).json()
    assert result["status"] == "failed_permanent"
    assert result["failure_code"] == (
        "INVALID_IMAGE" if failure == "corrupt" else "IMAGE_PIXEL_LIMIT"
    )
    assert result["text"] == "" and result["details"] == {}
    assert (
        client.get(f"/api/v1/attachments/{message['attachments'][0]['id']}/download").status_code
        == 200
    )


def test_processing_role_workspace_and_model_absence_boundaries(product, tmp_path):
    from tests.security.test_product_access import login_as

    client, app, worker = product
    message, _ = image_source(product)
    payload = {"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]}
    valid_models = app.state.settings.ocr_data_dir
    app.state.settings.ocr_data_dir = tmp_path / "missing-models"
    assert not client.get("/api/v1/processing/capabilities").json()["modules"]["ocr"]["available"]
    assert client.patch("/api/v1/processing/modules/ocr", json={"enabled": True}).status_code == 409
    app.state.settings.ocr_data_dir = valid_models
    client.patch("/api/v1/processing/modules/ocr", json={"enabled": True})
    result = client.post("/api/v1/process/ocr", json=payload).json()
    for role in ("reader", "reviewer"):
        assert (
            client.post(
                "/api/v1/users",
                json={"username": role, "password": "synthetic-test-password", "role": role},
            ).status_code
            == 201
        )
        with TestClient(app) as other:
            login_as(other, role)
            assert (
                other.patch("/api/v1/processing/modules/ocr", json={"enabled": False}).status_code
                == 403
            )
            assert other.post("/api/v1/process/ocr", json=payload).status_code == (
                403 if role == "reader" else 202
            )
            assert other.get("/api/v1/processing/results/" + result["result_id"]).status_code == 200
    with app.state.factory.begin() as session:
        workspace = Workspace(name="foreign synthetic workspace")
        user = User(
            username="foreign-processing", password_hash=password_hash("synthetic-test-password")
        )
        session.add_all([workspace, user])
        session.flush()
        session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="admin"))
    with TestClient(app) as other:
        login_as(other, "foreign-processing")
        assert other.get("/api/v1/processing/results/" + result["result_id"]).status_code == 404
        assert (
            other.get(
                "/api/v1/processing/results", params={"message_id": message["id"]}
            ).status_code
            == 404
        )
        assert other.post("/api/v1/process/ocr", json=payload).status_code == 404
        assert not other.get("/api/v1/processing/capabilities").json()["modules"]["ocr"]["enabled"]


def test_processing_lease_is_fenced_after_computation(product, monkeypatch):
    from wdh_api import processing

    client, app, worker = product
    message, _ = image_source(product)
    client.patch("/api/v1/processing/modules/ocr", json={"enabled": True})
    queued = client.post(
        "/api/v1/process/ocr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()

    def lost(*args):
        with app.state.factory.begin() as session:
            job = session.get(Job, queued["job_id"])
            job.lease_token = "new-worker-token"
        return "must never be committed", {}

    monkeypatch.setattr(processing, "ocr", lost)
    assert worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued["result_id"]).json()
    assert result["status"] == "running" and result["text"] == ""


def test_merging_duplicate_message_keeps_recognition_results_and_original_attachment(product):
    from wdh_api.routes import columns
    from wdh_domain.models import Message, Review

    client, app, worker = product
    message, original = image_source(product)
    client.patch("/api/v1/processing/modules/ocr", json={"enabled": True})
    result = client.post(
        "/api/v1/process/ocr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()
    worker.run_once()
    with app.state.factory.begin() as session:
        old = session.get(Message, message["id"])
        values = columns(old, {"id", "created_at", "updated_at", "strong_key"})
        new = Message(**values)
        session.add(new)
        session.flush()
        review = Review(
            workspace_id=old.workspace_id,
            review_type="duplicate",
            review_key="synthetic-ocr-merge",
            payload={"message_ids": [new.id, old.id]},
        )
        session.add(review)
        session.flush()
        target_id, review_id = new.id, review.id
    response = client.post(
        "/api/v1/reviews/" + review_id + "/resolve",
        json={"action": "merge", "reason": "核对两个合成重复来源"},
    )
    assert response.status_code == 200, response.text
    merged = client.get("/api/v1/messages/" + target_id).json()
    assert merged["processing_results"][0]["id"] == result["result_id"]
    assert (
        client.get("/api/v1/processing/results/" + result["result_id"]).json()["message_id"]
        == target_id
    )
    assert (
        client.get("/api/v1/attachments/" + message["attachments"][0]["id"] + "/download").content
        == original
    )
