import io
import json
import tarfile

from fastapi.testclient import TestClient
from wdh_api.backup import EncryptedReader
from wdh_api.demo import demo_zip
from wdh_api.security import password_hash
from wdh_domain.models import Membership, User, Workspace

from tests.integration.test_product import initialize, upload
from tests.security.test_product_access import login_as


def test_workspace_admin_backup_does_not_include_other_workspaces_or_credentials(product):
    client, app, worker = product
    initialize(client)
    upload(client, demo_zip())
    worker.run_once()
    with app.state.factory.begin() as session:
        workspace = Workspace(name="synthetic isolated workspace")
        user = User(
            username="isolated-admin", password_hash=password_hash("synthetic-test-password")
        )
        session.add_all([workspace, user])
        session.flush()
        session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="admin"))
    with TestClient(app) as isolated:
        login_as(isolated, "isolated-admin")
        result = isolated.post("/api/v1/backups", json={"password": "synthetic-backup-passphrase"})
        assert result.status_code == 200, result.text
    reader = EncryptedReader(io.BytesIO(result.content), "synthetic-backup-passphrase")
    tables = {}
    with tarfile.open(fileobj=reader, mode="r|") as archive:
        for member in archive:
            file = archive.extractfile(member)
            if member.name.startswith("database/"):
                tables[member.name] = [json.loads(line) for line in file.read().splitlines()]
    reader.finish()
    assert len(tables["database/workspaces.jsonl"]) == 1
    assert tables["database/workspaces.jsonl"][0]["name"] == "synthetic isolated workspace"
    assert tables["database/messages.jsonl"] == []
    assert tables["database/source_blobs.jsonl"] == []
    assert [row["username"] for row in tables["database/users.jsonl"]] == ["isolated-admin"]
