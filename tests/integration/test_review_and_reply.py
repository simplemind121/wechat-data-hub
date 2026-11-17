import json

from wdh_api.demo import demo_zip

from tests.integration.test_product import initialize, upload


def test_defer_then_merge_keeps_all_raw_observations(product):
    client, _, worker = product
    initialize(client)
    upload(client, demo_zip())
    worker.run_once()
    row = next(
        item
        for item in client.get("/api/v1/reviews").json()["items"]
        if item["review_type"] == "duplicate"
    )
    path = "/api/v1/reviews/" + row["id"] + "/resolve"
    assert (
        client.post(path, json={"action": "defer", "reason": "暂缓核对原始来源"}).status_code == 200
    )
    assert client.get("/api/v1/overview").json()["messages"] == 5
    assert (
        client.post(path, json={"action": "merge", "reason": "核对后确认来源重复"}).status_code
        == 200
    )
    assert client.get("/api/v1/overview").json()["messages"] == 4
    result = client.get("/api/v1/search?q=收到").json()["items"]
    assert len(result) == 1 and result[0]["observation_count"] == 2
    detail = client.get("/api/v1/messages/" + result[0]["id"]).json()
    assert len(detail["observations"]) == 2


def test_reply_resolution_uses_source_batch_and_never_guesses_foreign_device_ids(product):
    client, _, worker = product
    initialize(client)
    source = {
        "account_ref": "synthetic",
        "device_ref": "device-a",
        "platform": "other",
        "data_format": "jsonl-v1",
        "exported_at": "2026-11-17T12:30:00Z",
        "original_timezone": "UTC",
    }

    def send(device, records):
        source["device_ref"] = device
        payload = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in records)
        result = client.post(
            "/api/v1/imports",
            files={"file": ("messages.jsonl", payload)},
            data={"source": json.dumps(source)},
        )
        assert result.status_code == 202
        worker.run_once()

    common = {
        "conversation_ref": "same-conversation",
        "sender_ref": "same-sender",
        "message_type": "text",
        "sent_at": "2026-11-17T12:00:00Z",
    }
    send("device-a", [{**common, "source_record_id": "1", "body_text": "设备A原文"}])
    send(
        "device-b", [{**common, "source_record_id": "2", "body_text": "设备B引用", "reply_to": "1"}]
    )
    reply = client.get("/api/v1/search?q=设备B引用").json()["items"][0]
    assert reply["reply_to_id"] is None
    send("device-b", [{**common, "source_record_id": "1", "body_text": "设备B原文"}])
    reply = client.get("/api/v1/search?q=设备B引用").json()["items"][0]
    target = client.get("/api/v1/search?q=设备B原文").json()["items"][0]
    assert reply["reply_to_id"] == target["id"]
