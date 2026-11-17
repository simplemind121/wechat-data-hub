import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from tests.integration.test_product import initialize


@pytest.mark.parametrize("format", ["jsonl-v1", "json-v1", "csv-v1"])
def test_user_declared_upload_generates_actual_manifest_and_imports_all_formats(product, format):
    client, _, worker = product
    initialize(client)
    record = {
        "source_record_id": "synthetic-format-1",
        "conversation_ref": "合成会话",
        "sender_ref": "synthetic-sender",
        "sent_at": "2026-11-17T19:30:00+08:00",
        "message_type": "text",
        "body_text": "格式测试：中文🧪",
    }
    source = {
        "account_ref": "synthetic-account",
        "device_ref": "synthetic-device",
        "platform": "other",
        "data_format": format,
        "exporter_name": "unknown",
        "exporter_version": "unknown",
        "exported_at": "2026-11-17T12:00:00Z",
        "original_timezone": "Asia/Shanghai",
    }
    if format == "csv-v1":
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(record))
        writer.writeheader()
        writer.writerow(record)
        payload = buffer.getvalue().encode()
        source["field_mapping"] = {key: key for key in record}
        name = "messages.csv"
    elif format == "json-v1":
        payload = json.dumps([record], ensure_ascii=False).encode()
        name = "messages.json"
    else:
        payload = (json.dumps(record, ensure_ascii=False) + "\n").encode()
        name = "messages.jsonl"
    response = client.post(
        "/api/v1/imports", files={"file": (name, payload)}, data={"source": json.dumps(source)}
    )
    assert response.status_code == 202, response.text
    worker.run_once()
    assert (
        client.get("/api/v1/search?q=中文").json()["items"][0]["body_text"] == record["body_text"]
    )
    coverage = client.get(f"/api/v1/imports/{response.json()['import_id']}/coverage").json()
    assert coverage["source"]["payload_files"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert coverage["source"]["manifest_origin"] == "user-declared-generated"
    repeated = client.post(
        "/api/v1/imports", files={"file": (name, payload)}, data={"source": json.dumps(source)}
    )
    assert repeated.json()["status"] == "already_ingested"


def media_bundle():
    import zipfile

    from wdh_api.demo import demo_zip

    pixel = Path("tests/fixtures/generated-v1/ios/media/pixel.png").read_bytes()
    with zipfile.ZipFile(io.BytesIO(demo_zip())) as original:
        manifest = original.read("manifest.json")
        rows = [json.loads(line) for line in original.read("messages.jsonl").splitlines()]
    rows[-1]["media"] = [{"path": "media/pixel.png"}]
    data = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)
    declaration = json.loads(manifest)
    declaration["payload_files"][0].update(
        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest()
    )
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr("manifest.json", json.dumps(declaration))
        archive.writestr("messages.jsonl", data)
        archive.writestr("media/pixel.png", pixel)
    return packed.getvalue(), pixel


def test_present_attachment_sniff_and_authenticated_download(product):
    client, _, worker = product
    initialize(client)
    data, pixel = media_bundle()
    result = client.post("/api/v1/imports", files={"file": ("media.zip", data)})
    assert result.status_code == 202
    worker.run_once()
    message = next(
        row for row in client.get("/api/v1/search").json()["items"] if row["attachments"]
    )
    attachment = message["attachments"][0]
    downloaded = client.get(f"/api/v1/attachments/{attachment['id']}/download")
    assert downloaded.content == pixel
    assert downloaded.headers["Content-Type"] == "image/png"
    assert downloaded.headers["Content-Disposition"].startswith("attachment;")
    assert attachment["sha256"] == hashlib.sha256(pixel).hexdigest()
