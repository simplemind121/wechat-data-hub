from pathlib import Path

from wdh_api.demo import demo_zip

from tests.integration.test_product import initialize, upload


def prepared(product):
    client, app, worker = product
    initialize(client)
    app.state.settings.local_model_server = Path(".local/models/runtime/llama-server").resolve()
    app.state.settings.embedding_model_file = Path(
        ".local/models/embedding/bge-small-zh-v1.5-q8_0.gguf"
    ).resolve()
    upload(client, demo_zip())
    worker.run_once()
    message = client.get("/api/v1/search?q=M620").json()["items"][0]
    return message


def test_real_local_embedding_requires_business_permission_and_returns_cited_search(product):
    client, _, worker = product
    message = prepared(product)
    enabled = client.patch("/api/v1/processing/modules/embedding", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert (
        client.post("/api/v1/process/embedding", json={"message_id": message["id"]}).status_code
        == 403
    )
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "business_approved"},
    )
    result = client.post("/api/v1/process/embedding", json={"message_id": message["id"]})
    assert result.status_code == 202, result.text
    assert worker.run_once()
    result = client.get("/api/v1/processing/results/" + result.json()["result_id"]).json()
    assert result["status"] == "completed", result
    assert all(len(chunk["vector"]) == 512 for chunk in result["details"]["chunks"])
    response = client.get("/api/v1/semantic/search", params={"q": "M620的价格是多少"})
    assert response.status_code == 200, response.text
    hit = response.json()["items"][0]
    assert hit["message"]["id"] == message["id"]
    assert hit["citation"]["message_id"] == message["id"]
    assert hit["citation"]["source_span"] in message["body_text"]
    assert hit["similarity"] > 0.3
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "private"},
    )
    assert client.get("/api/v1/semantic/search", params={"q": "M620"}).json()["items"] == []
    assert client.get("/api/v1/processing/results/" + result["id"]).status_code == 403


def test_hybrid_search_keeps_keyword_matches_and_exact_source_citations(product):
    client, _, worker = product
    message = prepared(product)
    client.patch(
        f"/api/v1/conversations/{message['conversation_id']}/privacy",
        json={"privacy_scope": "business_approved"},
    )
    client.patch("/api/v1/processing/modules/embedding", json={"enabled": True})
    client.post("/api/v1/process/embedding", json={"message_id": message["id"]})
    worker.run_once()
    response = client.get("/api/v1/semantic/search", params={"q": "M620 3200", "mode": "hybrid"})
    assert response.status_code == 200, response.text
    hit = response.json()["items"][0]
    assert hit["rank_score"] > 0 and hit["matched_by"] == ["semantic", "keyword"]
    assert hit["citation"]["source_span"] in message["body_text"]
