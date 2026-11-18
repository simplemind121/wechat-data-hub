"""Real local weights for positive paths; adversarial provider output is separately labelled."""

import json
from pathlib import Path

from tests.integration.test_semantic import prepared


def llm_settings(settings):
    marker = Path(".local/llm-memory.json")
    settings.llm_model_file = (
        Path(json.loads(marker.read_text())["path"])
        if marker.is_file()
        else Path(".local/models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf").resolve()
    )


def allowed_source(product):
    client, app, _ = product
    message = prepared(product)
    llm_settings(app.state.settings)
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "business_approved"},
    )
    for kind in ("embedding", "llm"):
        response = client.patch("/api/v1/processing/modules/" + kind, json={"enabled": True})
        assert response.status_code == 200, response.text
    return message


def test_real_llm_candidates_are_pending_and_fields_have_original_evidence(product):
    client, _, worker = product
    message = allowed_source(product)
    queued = client.post("/api/v1/process/llm", json={"message_id": message["id"]})
    assert queued.status_code == 202, queued.text
    worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued.json()["result_id"]).json()
    assert result["status"] == "completed", result
    assert result["text"] and all(
        s["source_span"] in message["body_text"] for s in result["details"]["summary_spans"]
    )
    assert result["details"]["entity_ids"], result
    entities = client.get("/api/v1/entities").json()["items"]
    for entity in entities:
        assert entity["review_status"] == "pending" and entity["approved_payload"] is None
        assert all(
            e["source_span"] in message["body_text"]
            for e in entity["evidence"]
            if e["field"] != "supplier_ref"
        )
        assert (
            client.post(
                "/api/v1/integrations/odoo/dry-run", json={"entity_ids": [entity["id"]]}
            ).status_code
            == 409
        )
    assert (
        client.post("/api/v1/process/llm", json={"message_id": message["id"]}).json()["job_id"]
        == queued.json()["job_id"]
    )


def test_real_cited_question_answer_and_unknown_question(product):
    client, _, worker = product
    message = allowed_source(product)
    client.post("/api/v1/process/embedding", json={"message_id": message["id"]})
    worker.run_once()
    response = client.post("/api/v1/semantic/ask", json={"question": "M620的价格是多少"})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["supported"] is True and answer["citations"]
    assert "3200" in answer["answer"]
    assert all(
        c["message_id"] == message["id"] and c["source_span"] in message["body_text"]
        for c in answer["citations"]
    )
    unknown = client.post(
        "/api/v1/semantic/ask", json={"question": "2029年火星基地的租金是多少"}
    ).json()
    assert unknown["supported"] is False and unknown["citations"] == []
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "private"},
    )
    assert not client.post("/api/v1/semantic/ask", json={"question": "M620的价格是多少"}).json()[
        "supported"
    ]


def test_untrusted_model_output_cannot_introduce_fields_without_source_evidence(
    product, monkeypatch
):
    from sqlalchemy import select
    from wdh_api import ai
    from wdh_domain.models import EntityAssertion

    client, app, worker = product
    message = allowed_source(product)
    # This is an adversarial provider contract test, separate from the real-weight tests above.
    monkeypatch.setattr(
        ai,
        "native_request",
        lambda *args: {
            "output": {
                "summary": [{"source_span": "虚构已付款"}],
                "entities": [
                    {
                        "entity_type": "quotation",
                        "fields": [
                            {"name": "product_model", "source_span": "M620"},
                            {"name": "unit_price", "source_span": "999999"},
                            {"name": "currency", "source_span": "元"},
                        ],
                    }
                ],
            }
        },
    )
    queued = client.post("/api/v1/process/llm", json={"message_id": message["id"]}).json()
    worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued["result_id"]).json()
    assert result["status"] == "completed" and result["text"] == ""
    assert (
        not result["details"]["entity_ids"] and len(result["details"]["rejected_candidates"]) == 2
    )
    with app.state.factory() as session:
        assert not list(session.scalars(select(EntityAssertion)))


def test_rag_rechecks_permission_after_inference_and_disabled_flag(product, monkeypatch):
    from wdh_api import processing
    from wdh_domain.models import Conversation

    client, app, worker = product
    message = allowed_source(product)
    client.post("/api/v1/process/embedding", json={"message_id": message["id"]})
    worker.run_once()
    original = processing.native_request

    def revoke(settings, kind, data):
        if kind == "llm":
            with app.state.factory.begin() as session:
                session.get(Conversation, message["conversation_id"]).privacy_scope = "private"
            return {"output": {"indices": [0]}}
        return original(settings, kind, data)

    monkeypatch.setattr(processing, "native_request", revoke)
    response = client.post("/api/v1/semantic/ask", json={"question": "M620的价格是多少"})
    assert response.status_code == 200 and not response.json()["supported"], response.text
    client.patch("/api/v1/processing/modules/llm", json={"enabled": False})
    assert (
        client.post("/api/v1/semantic/ask", json={"question": "M620的价格是多少"}).status_code
        == 409
    )


def test_real_ocr_text_can_feed_local_llm_and_approved_fields_remain_traceable(product):
    from tests.integration.test_processing import image_source

    client, app, worker = product
    message, _ = image_source(product)
    # The OCR helper has imported an image but has not recognized it yet.
    llm_settings(app.state.settings)
    app.state.settings.local_model_server = Path(".local/models/runtime/llama-server").resolve()
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "business_approved"},
    )
    for kind in ("ocr", "llm"):
        assert (
            client.patch("/api/v1/processing/modules/" + kind, json={"enabled": True}).status_code
            == 200
        )
    queued = client.post(
        "/api/v1/process/ocr",
        json={"message_id": message["id"], "attachment_id": message["attachments"][0]["id"]},
    ).json()
    worker.run_once()
    ocr = client.get("/api/v1/processing/results/" + queued["result_id"]).json()
    queued = client.post(
        "/api/v1/process/llm", json={"message_id": message["id"], "source_result_id": ocr["id"]}
    )
    assert queued.status_code == 202, queued.text
    worker.run_once()
    result = client.get("/api/v1/processing/results/" + queued.json()["result_id"]).json()
    assert result["status"] == "completed" and result["details"]["entity_ids"], result
    entity = next(
        e
        for e in client.get("/api/v1/entities").json()["items"]
        if e["id"] in result["details"]["entity_ids"]
    )
    assert all(
        e.get("source_result_id") == ocr["id"]
        for e in entity["evidence"]
        if e["field"] != "supplier_ref"
    )
    assert (
        client.post(
            "/api/v1/entities/" + entity["id"] + "/approve",
            json={"decision": "approve", "reason": "核对合成原图与识别文字"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/integrations/odoo/dry-run", json={"entity_ids": [entity["id"]]}
        ).json()["remote_writes"]
        is False
    )


def test_private_revocation_hides_existing_business_candidates(product):
    client, _, _ = product
    message = allowed_source(product)
    assert (
        client.post("/api/v1/entities/extract", json={"message_id": message["id"]}).status_code
        == 201
    )
    assert client.get("/api/v1/entities").json()["items"]
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "private"},
    )
    assert client.get("/api/v1/entities").json()["items"] == []
