import io
import json
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import select
from wdh_api.demo import demo_zip
from wdh_api.security import password_hash
from wdh_domain.models import Membership, User, Workspace

from tests.integration.test_product import initialize, upload


def login_as(client: TestClient, username: str) -> None:
    result = client.post(
        "/api/v1/auth/login", json={"username": username, "password": "synthetic-test-password"}
    )
    assert result.status_code == 200, result.text
    client.headers["x-csrf-token"] = result.json()["csrf_token"]


def test_session_csrf_setup_once_and_password_not_stored_plaintext(product) -> None:
    client, app, _ = product
    assert client.get("/api/v1/imports").status_code == 401
    assert client.post("/api/v1/imports").status_code == 401
    initialize(client)
    assert (
        client.post(
            "/api/v1/auth/setup", json={"username": "other", "password": "synthetic-test-password"}
        ).status_code
        == 409
    )
    token = client.headers.pop("x-csrf-token")
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers["x-csrf-token"] = token
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.get("/api/v1/me", headers={"Host": "evil.example"}).status_code == 400
    with app.state.factory() as session:
        user = session.scalar(select(User))
        assert user.password_hash.startswith("scrypt-v1$")
        assert "synthetic-test-password" not in user.password_hash


def test_reader_and_reviewer_permissions_and_export_boundary(product) -> None:
    client, app, worker = product
    initialize(client)
    first = upload(client, demo_zip())
    worker.run_once()
    for role in ("reader", "reviewer"):
        response = client.post(
            "/api/v1/users",
            json={"username": role, "password": "synthetic-test-password", "role": role},
        )
        assert response.status_code == 201
    with TestClient(app) as reader:
        login_as(reader, "reader")
        assert reader.get("/api/v1/conversations").status_code == 200
        assert reader.get("/api/v1/search?q=收到").status_code == 200
        for path in ("/imports", "/audit", "/exports/messages", "/reviews", "/users"):
            assert reader.get("/api/v1" + path).status_code == 403
        assert (
            reader.post("/api/v1/imports", files={"file": ("x.zip", demo_zip())}).status_code == 403
        )
        assert reader.post(f"/api/v1/imports/{first['import_id']}/retry").status_code == 403
    with TestClient(app) as reviewer:
        login_as(reviewer, "reviewer")
        assert reviewer.get("/api/v1/reviews").status_code == 200
        assert reviewer.get("/api/v1/imports").status_code == 200
        assert reviewer.get("/api/v1/exports/messages").status_code == 403
        assert (
            reviewer.post(
                "/api/v1/users",
                json={"username": "forbidden", "password": "synthetic-test-password"},
            ).status_code
            == 403
        )


def test_foreign_workspace_idor_for_all_object_routes_and_filters(product) -> None:
    client, app, worker = product
    initialize(client)
    first = upload(client, demo_zip())
    worker.run_once()
    overview = client.get("/api/v1/overview").json()
    message = client.get("/api/v1/search").json()["items"][0]
    conversation = message["conversation_id"]
    attachment = next(
        row for row in client.get("/api/v1/search").json()["items"] if row["attachments"]
    )["attachments"][0]["id"]
    with app.state.factory.begin() as session:
        workspace = Workspace(name="synthetic foreign workspace")
        user = User(username="foreign-user", password_hash=password_hash("synthetic-test-password"))
        session.add_all([workspace, user])
        session.flush()
        session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="admin"))
    with TestClient(app) as foreign:
        login_as(foreign, "foreign-user")
        for path in (
            f"/messages/{message['id']}",
            f"/conversations/{conversation}/messages",
            f"/attachments/{attachment}/download",
            f"/imports/{first['import_id']}/coverage",
            f"/imports/{first['import_id']}/errors",
            f"/jobs/{first['job_id']}",
        ):
            assert foreign.get("/api/v1" + path).status_code == 404, path
        for query in (
            f"conversation_id={conversation}",
            f"account_id={overview['accounts'][0]['id']}",
            f"device_id={overview['sources'][0]['id']}",
            f"cursor={message['id']}",
        ):
            assert foreign.get("/api/v1/search?" + query).status_code == 404
        assert foreign.get("/api/v1/search?q=M620").json()["items"] == []
        assert foreign.post(f"/api/v1/imports/{first['import_id']}/retry").status_code == 404


def test_login_limit_and_session_invalidation(product) -> None:
    client, app, _ = product
    initialize(client)
    for _ in range(8):
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "owner", "password": "wrong-long-password"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "synthetic-test-password"}
        ).status_code
        == 429
    )
    stolen_cookie = client.cookies.get("wdh_session")
    assert client.post("/api/v1/auth/logout").status_code == 200
    with TestClient(app) as stale:
        stale.cookies.set("wdh_session", stolen_cookie)
        assert stale.get("/api/v1/me").status_code == 401


def test_zip_slip_bomb_and_hash_mismatch_rejected_before_job_creation(product) -> None:
    client, _, _ = product
    initialize(client)
    for name in ("../escape", "/absolute", "C:/windows", "a\\b"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(name, "synthetic")
        result = client.post("/api/v1/imports", files={"file": ("attack.zip", buffer.getvalue())})
        assert result.status_code == 400
        assert "synthetic" not in result.text
    with zipfile.ZipFile(io.BytesIO(demo_zip())) as original:
        manifest = json.loads(original.read("manifest.json"))
        manifest["payload_files"][0]["sha256"] = "0" * 64
        payload = original.read("messages.jsonl")
    result = client.post(
        "/api/v1/imports",
        data={"manifest": json.dumps(manifest)},
        files={"file": ("messages.jsonl", payload)},
    )
    assert result.status_code == 400
    assert result.json()["code"] == "PAYLOAD_CHECKSUM_MISMATCH"
    assert client.get("/api/v1/overview").json()["imports"] == 0


def test_admin_export_escapes_csv_formulas_without_changing_jsonl(product) -> None:
    client, _, worker = product
    initialize(client)
    with zipfile.ZipFile(io.BytesIO(demo_zip())) as original:
        manifest = json.loads(original.read("manifest.json"))
        rows = [json.loads(line) for line in original.read("messages.jsonl").splitlines()]
    rows[0]["body_text"] = '=HYPERLINK("https://evil.example")'
    payload = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)
    import hashlib

    manifest["payload_files"][0].update(
        size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()
    )
    result = client.post(
        "/api/v1/imports",
        data={"manifest": json.dumps(manifest)},
        files={"file": ("messages.jsonl", payload)},
    )
    assert result.status_code == 202
    worker.run_once()
    csv = client.get("/api/v1/exports/messages?format=csv").text
    assert "'=HYPERLINK" in csv
    source = [json.loads(line) for line in client.get("/api/v1/exports/messages").text.splitlines()]
    assert any(row["body_text"] == rows[0]["body_text"] for row in source)
