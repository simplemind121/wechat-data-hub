"""Timeout/approval/outbox fixtures; no remote Odoo instance is claimed."""

import json
from unittest.mock import patch

import httpx
from pydantic import SecretStr
from wdh_api.odoo_sync import deliver

from tests.integration.test_entities import business_source
from tests.integration.test_product import initialize


def approved(product):
    client, app, worker = product
    initialize(client)
    message = business_source(client, worker)
    row = client.post("/api/v1/entities/extract", json={"message_id": message["id"]}).json()
    client.post(
        f"/api/v1/entities/{row['id']}/approve",
        json={"decision": "approve", "reason": "合成报价字段逐项核对"},
    )
    config = app.state.settings
    config.enable_odoo = config.enable_odoo_writes = True
    config.odoo_url, config.odoo_database, config.odoo_username = (
        "https://synthetic.invalid",
        "fixture",
        "fixture",
    )
    config.odoo_api_key = SecretStr("synthetic-only")
    return client, app, worker, row, message


def order(row):
    return {
        "entity_id": row["id"],
        "target_model": "purchase.order",
        "mapping": {
            "partner_id": 1,
            "product_id": 2,
            "currency_id": 3,
            "uom_id": 4,
            "quantity": "60",
        },
        "confirm": True,
    }


def test_approved_outbox_and_lost_response_retry_produces_one_remote_draft(product):
    client, app, worker, row, _ = approved(product)
    data = order(row)
    queued = client.post("/api/v1/integrations/odoo/sync", json=data)
    assert queued.status_code == 202, queued.text
    assert (
        client.post("/api/v1/integrations/odoo/sync", json=data).json()["job_id"]
        == queued.json()["job_id"]
    )
    changed = {**data, "mapping": {**data["mapping"], "quantity": "61"}}
    assert client.post("/api/v1/integrations/odoo/sync", json=changed).status_code == 409
    remote, lost = {}, True

    def fixture(request):
        nonlocal lost
        envelope = json.loads(request.content)
        params = envelope["params"]
        if params["method"] == "authenticate":
            result = 42
        else:
            args = params["args"]
            model, method, call = args[3:6]
            assert method not in {"write", "unlink", "action_confirm", "button_confirm"}
            if method == "apply_approved":
                key, target, values = call
                assert values["order_line"][0][2]["product_qty"] == 60
                remote.setdefault(key, {"remote_id": 99, "model": target})
                if lost:
                    lost = False
                    raise httpx.ReadTimeout("synthetic response loss", request=request)
                result = remote[key]
            elif model == "res.currency":
                result = [{"id": 3, "name": "CNY"}]
            elif model == "purchase.order.line":
                result = [
                    {
                        "id": 100,
                        "product_id": [2, "M620"],
                        "product_uom_id": [4, "套"],
                        "product_qty": 60,
                        "price_unit": 3200,
                    }
                ]
            else:
                assert model == "purchase.order" and method == "read"
                result = [
                    {
                        "id": 99,
                        "name": "SYNTHETIC RFQ",
                        "state": "draft",
                        "partner_id": [1, "fixture"],
                        "currency_id": [3, "CNY"],
                        "order_line": [100],
                    }
                ]
        return httpx.Response(200, json={"id": envelope["id"], "result": result})

    transport = httpx.MockTransport(fixture)
    original = deliver
    with patch(
        "wdh_api.odoo_sync.deliver", side_effect=lambda w, j, t: original(w, j, t, transport)
    ):
        assert worker.run_once()
        assert len(remote) == 1
        outbox = client.get("/api/v1/integrations/odoo/outbox").json()["items"][0]
        assert outbox["status"] == "failed_retryable"
        assert (
            client.post(f"/api/v1/integrations/odoo/outbox/{outbox['id']}/retry").status_code == 200
        )
        assert worker.run_once()
    outbox = client.get("/api/v1/integrations/odoo/outbox").json()["items"][0]
    assert outbox["status"] == "completed" and outbox["remote_id"] == 99
    assert len(remote) == 1


def test_queued_draft_rechecks_privacy_and_disable_before_dispatch(product):
    client, app, worker, row, message = approved(product)
    data = order(row)
    assert client.post("/api/v1/integrations/odoo/plan", json=data).json()["remote_writes"] is False
    assert client.post("/api/v1/integrations/odoo/sync", json=data).status_code == 202
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "private"},
    )
    with patch("wdh_api.odoo_sync.Rpc", side_effect=AssertionError("No remote access permitted")):
        assert worker.run_once()
    status = client.get("/api/v1/integrations/odoo/outbox").json()["items"][0]
    assert status["status"] == "failed_retryable"
    app.state.settings.enable_odoo_writes = False
    assert client.post("/api/v1/integrations/odoo/sync", json=data).status_code == 409


def test_quantity_is_explicit_and_moq_is_not_implicitly_used(product):
    client, _, _, row, _ = approved(product)
    missing = order(row)
    del missing["mapping"]["quantity"]
    assert client.post("/api/v1/integrations/odoo/plan", json=missing).status_code == 422
    result = client.post("/api/v1/integrations/odoo/plan", json=order(row)).json()
    assert result["values"]["order_line"][0][2]["product_qty"] == 60
