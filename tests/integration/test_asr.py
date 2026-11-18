import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from tests.integration.test_processing import processing_image_bundle
from tests.integration.test_product import initialize, upload


def audio_bundle(audio: bytes | None = None) -> tuple[bytes, bytes]:
    audio = audio or Path("tests/fixtures/asr-v1/synthetic-speech.wav").read_bytes()
    source, _ = processing_image_bundle(audio)
    with zipfile.ZipFile(io.BytesIO(source)) as original:
        manifest = json.loads(original.read("manifest.json"))
        rows = [json.loads(line) for line in original.read("messages.jsonl").splitlines()]
    rows[-1].update(
        message_type="audio",
        body_text="合成语音测试，转录需核对原音频",
        media=[{"path": "media/synthetic.wav"}],
    )
    payload = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)
    manifest["payload_files"][0].update(
        size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("messages.jsonl", payload)
        archive.writestr("media/synthetic.wav", audio)
    return buffer.getvalue(), audio


def source(product, audio=None):
    client, app, worker = product
    initialize(client)
    app.state.settings.asr_model_dir = Path(".local/models/asr").resolve()
    packed, original = audio_bundle(audio)
    upload(client, packed)
    worker.run_once()
    message = next(r for r in client.get("/api/v1/search").json()["items"] if r["attachments"])
    return message, original


@pytest.mark.parametrize("codec", ["wav", "ogg", "flac", "mp3"])
def test_real_whisper_transcription_has_audio_hash_and_bounded_segment_times(product, codec):
    client, _, worker = product
    message, original = source(
        product, Path(f"tests/fixtures/asr-v1/synthetic-speech.{codec}").read_bytes()
    )
    payload = {"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]}
    assert client.post("/api/v1/process/asr", json=payload).status_code == 409
    enabled = client.patch("/api/v1/processing/modules/asr", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    queued = client.post("/api/v1/process/asr", json=payload)
    assert queued.status_code == 202, queued.text
    worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued.json()["result_id"]).json()
    assert result["status"] == "completed", result
    assert "synthetic" in result["text"].casefold() and "price" in result["text"].casefold()
    assert result["source_sha256"] == hashlib.sha256(original).hexdigest()
    details = result["details"]
    assert details["timestamp_granularity"] == "segment" and details["uncertain"]
    assert details["segments"]
    assert all(
        0 <= s["start"] < s["end"] <= details["duration_seconds"] + 0.001
        for s in details["segments"]
    )
    assert result["provider_version"].startswith("sherpa-whisper/")
    assert (
        client.post("/api/v1/process/asr", json=payload).json()["job_id"] == queued.json()["job_id"]
    )
    assert any(
        r["id"] == message["id"] for r in client.get("/api/v1/search?q=synthetic").json()["items"]
    )
    assert (
        client.get(f"/api/v1/attachments/{payload['attachment_id']}/download").content == original
    )


@pytest.mark.parametrize(
    "case,code", [("duration", "AUDIO_DURATION_LIMIT"), ("corrupt", "UNSUPPORTED_AUDIO_CODEC")]
)
def test_audio_error_never_fabricates_transcription(product, case, code):
    client, app, worker = product
    data = b"RIFF0000WAVEsynthetic-invalid-audio" if case == "corrupt" else None
    message, _ = source(product, data)
    if case == "duration":
        app.state.settings.asr_max_seconds = 1
    client.patch("/api/v1/processing/modules/asr", json={"enabled": True})
    queued = client.post(
        "/api/v1/process/asr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()
    worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued["result_id"]).json()
    assert result["status"] == "failed_permanent", result
    assert result["failure_code"] == code
    assert result["text"] == "" and result["details"] == {}
