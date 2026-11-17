from wdh_api.demo import demo_zip

from tests.integration.test_product import initialize, upload


def business_source(client, worker):
    upload(client, demo_zip())
    worker.run_once()
    message = client.get("/api/v1/search?q=M620").json()["items"][0]
    result = client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "business_approved"},
    )
    assert result.status_code == 200
    return message


def test_private_conversation_cannot_extract_and_every_approved_field_has_evidence(product):
    client, _, worker = product
    initialize(client)
    upload(client, demo_zip())
    worker.run_once()
    message = client.get("/api/v1/search?q=M620").json()["items"][0]
    assert (
        client.post("/api/v1/entities/extract", json={"message_id": message["id"]}).status_code
        == 403
    )
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "business_approved"},
    )
    candidate = client.post("/api/v1/entities/extract", json={"message_id": message["id"]})
    assert candidate.status_code == 201, candidate.text
    row = candidate.json()
    assert row["payload"]["unit_price"] == "3200"
    assert row["payload"]["currency"] == "CNY"
    assert row["payload"]["quantity_moq"] == "50"
    assert {e["field"] for e in row["evidence"]} == set(row["payload"])
    # No invented correction is accepted.
    bad = client.post(
        f"/api/v1/entities/{row['id']}/approve",
        json={
            "decision": "approve",
            "reason": "尝试虚构价格",
            "corrections": {"unit_price": "99999"},
        },
    )
    assert bad.status_code == 400
    approved = client.post(
        f"/api/v1/entities/{row['id']}/approve",
        json={"decision": "approve", "reason": "逐字段核对来源"},
    )
    assert approved.status_code == 200
    assert approved.json()["review_status"] == "approved"
    assert approved.json()["approved_payload"] == row["payload"]
    again = client.post("/api/v1/entities/extract", json={"message_id": message["id"]})
    assert again.json()["id"] == row["id"]


def test_odoo_dry_run_never_writes_and_requires_current_business_permission_and_approval(product):
    client, _, worker = product
    initialize(client)
    message = business_source(client, worker)
    candidate = client.post("/api/v1/entities/extract", json={"message_id": message["id"]}).json()
    data = {"entity_ids": [candidate["id"]]}
    assert client.post("/api/v1/integrations/odoo/dry-run", json=data).status_code == 409
    client.post(
        f"/api/v1/entities/{candidate['id']}/approve",
        json={"decision": "approve", "reason": "审核原始报价字段"},
    )
    dry = client.post("/api/v1/integrations/odoo/dry-run", json=data)
    assert dry.status_code == 200, dry.text
    assert dry.json()["remote_writes"] is False
    assert dry.json()["connection_verified"] is False
    assert dry.json()["plans"][0]["state"] == "draft"
    assert dry.json()["plans"][0]["remote_id"] is None
    repeated = client.post("/api/v1/integrations/odoo/dry-run", json=data).json()
    assert repeated["plans"][0]["idempotency_key"] == dry.json()["plans"][0]["idempotency_key"]
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "private"},
    )
    assert client.post("/api/v1/integrations/odoo/dry-run", json=data).status_code == 403
