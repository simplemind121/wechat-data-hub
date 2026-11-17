import json

from tests.integration.test_product import initialize


def test_same_nickname_stays_distinct_until_approval_then_search_includes_aliases(product):
    client, _, worker = product
    initialize(client)
    rows = [
        {
            "conversation_ref": "synthetic-conversation",
            "sender_ref": sender,
            "sender_name": "合成同名",
            "sent_at": "2026-11-17T12:00:00Z",
            "message_type": "text",
            "body_text": "来自" + sender,
        }
        for sender in ("synthetic-a", "synthetic-b")
    ]
    source = {
        "account_ref": "synthetic",
        "device_ref": "synthetic",
        "platform": "other",
        "data_format": "jsonl-v1",
        "exported_at": "2026-11-17T12:30:00Z",
        "original_timezone": "UTC",
    }
    payload = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)
    accepted = client.post(
        "/api/v1/imports",
        files={"file": ("messages.jsonl", payload)},
        data={"source": json.dumps(source)},
    )
    assert accepted.status_code == 202
    worker.run_once()
    contacts = client.get("/api/v1/contacts").json()["items"]
    assert len(contacts) == 2
    assert (
        len(client.get("/api/v1/search", params={"sender_id": contacts[0]["id"]}).json()["items"])
        == 1
    )
    review = next(
        row
        for row in client.get("/api/v1/reviews").json()["items"]
        if row["review_type"] == "identity"
    )
    assert (
        client.post(
            "/api/v1/reviews/" + review["id"] + "/resolve",
            json={"action": "merge", "reason": "明确核对来源后关联身份"},
        ).status_code
        == 200
    )
    assert (
        len(client.get("/api/v1/search", params={"sender_id": contacts[0]["id"]}).json()["items"])
        == 2
    )
    assert client.get("/api/v1/overview").json()["messages"] == 2
