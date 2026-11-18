"""Odoo contract tests use a labelled HTTP fixture; no real instance is claimed."""

import json

import httpx
from pydantic import SecretStr
from wdh_api import odoo
from wdh_api.config import Settings


def test_readonly_odoo_contract_never_invokes_remote_write_methods():
    calls = []

    def fixture(request):
        data = json.loads(request.content)
        params = data["params"]
        args = params["args"]
        calls.append(params)
        if params["method"] == "version":
            result = {"server_version": "19.0"}
        elif params["method"] == "authenticate":
            result = 42
        elif args[4] == "search_count":
            result = 0
        elif args[4] == "fields_get":
            result = {"name": {"type": "char"}}
        elif args[4] == "check_access_rights":
            result = True
        else:
            raise AssertionError("Unexpected remote method")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": data["id"], "result": result})

    settings = Settings(
        _env_file=None,
        enable_odoo=True,
        odoo_url="https://synthetic.invalid",
        odoo_database="synthetic",
        odoo_username="fixture",
        odoo_api_key=SecretStr("synthetic-not-a-real-key"),
    )
    report = odoo.check(settings, httpx.MockTransport(fixture))
    assert report["target_19_ce"] and not report["remote_writes"]
    assert report["draft_write_validation"] == "NOT_TESTED"
    assert all(
        c["args"][4] in {"search_count", "fields_get", "check_access_rights"}
        for c in calls
        if c["service"] == "object"
    )
    assert "synthetic-not-a-real-key" not in json.dumps(report)


def test_missing_odoo_and_disabled_flags_do_not_connect(product):
    client, _, _ = product
    from tests.integration.test_product import initialize

    initialize(client)
    response = client.post("/api/v1/integrations/odoo/test")
    assert response.status_code == 409 and response.json()["code"] == "ODOO_DISABLED"
    assert client.get("/api/v1/integrations/odoo/status").json()["real_validation"] == "BLOCKED"
