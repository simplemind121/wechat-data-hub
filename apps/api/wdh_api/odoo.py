"""Explicit, read-only Odoo JSON-RPC handshake. No remote create/write/confirm methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    import httpx

from wdh_api.config import Settings

MODELS = ("res.partner", "product.template", "purchase.order", "sale.order", "crm.lead")


class OdooCheckError(ValueError):
    pass


def configured(settings: Settings) -> bool:
    return bool(
        settings.odoo_url
        and settings.odoo_database
        and settings.odoo_username
        and settings.odoo_api_key
    )


def check(settings: Settings, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    if not settings.enable_odoo:
        raise OdooCheckError("ODOO_DISABLED")
    if not configured(settings):
        raise OdooCheckError("ODOO_NOT_CONFIGURED")
    import httpx

    parsed = urlsplit(settings.odoo_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise OdooCheckError("ODOO_INVALID_URL")
    counter = 0
    with httpx.Client(
        transport=transport, trust_env=False, timeout=10, follow_redirects=False
    ) as client:

        def rpc(service: str, method: str, args: list[Any]) -> Any:
            nonlocal counter
            counter += 1
            try:
                with client.stream(
                    "POST",
                    settings.odoo_url.rstrip("/") + "/jsonrpc",
                    json={
                        "jsonrpc": "2.0",
                        "method": "call",
                        "id": counter,
                        "params": {"service": service, "method": method, "args": args},
                    },
                ) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 2_097_152:
                            raise OdooCheckError("ODOO_RESPONSE_LIMIT")
                import json

                value = json.loads(content)
                if (
                    not isinstance(value, dict)
                    or value.get("id") != counter
                    or "error" in value
                    or "result" not in value
                ):
                    raise OdooCheckError("ODOO_RPC_REJECTED")
                return value["result"]
            except (httpx.HTTPError, ValueError) as exc:
                if isinstance(exc, OdooCheckError):
                    raise
                raise OdooCheckError("ODOO_CONNECTION_FAILED") from exc

        version = rpc("common", "version", [])
        if not isinstance(version, dict) or not isinstance(version.get("server_version"), str):
            raise OdooCheckError("ODOO_INVALID_VERSION")
        key = settings.odoo_api_key.get_secret_value() if settings.odoo_api_key else ""
        uid = rpc(
            "common", "authenticate", [settings.odoo_database, settings.odoo_username, key, {}]
        )
        if type(uid) is not int or uid <= 0:
            raise OdooCheckError("ODOO_AUTHENTICATION_FAILED")

        def execute(model: str, method: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
            return rpc(
                "object",
                "execute_kw",
                [settings.odoo_database, uid, key, model, method, args, kwargs],
            )

        edition = "unknown"
        try:
            installed = execute(
                "ir.module.module",
                "search_count",
                [[["name", "=", "web_enterprise"], ["state", "=", "installed"]]],
                {},
            )
            if type(installed) is int:
                edition = "Enterprise" if installed else "Community"
        except OdooCheckError:
            pass
        checks = []
        for model in MODELS:
            item: dict[str, Any] = {
                "model": model,
                "read": False,
                "create_permission": None,
                "fields": [],
            }
            try:
                fields = execute(
                    model, "fields_get", [], {"attributes": ["type", "required", "readonly"]}
                )
                if not isinstance(fields, dict):
                    raise OdooCheckError("ODOO_INVALID_SCHEMA")
                item["fields"] = sorted(fields)
                item["read"] = (
                    execute(model, "check_access_rights", ["read"], {"raise_exception": False})
                    is True
                )
                item["create_permission"] = (
                    execute(model, "check_access_rights", ["create"], {"raise_exception": False})
                    is True
                )
                item["status"] = "PASS" if item["read"] else "READ_DENIED"
            except OdooCheckError as exc:
                item["status"] = str(exc)
            checks.append(item)
        return {
            "connection_verified": True,
            "server_version": version["server_version"][:80],
            "edition": edition,
            "target_19_ce": version["server_version"].split(".")[0] == "19"
            and edition == "Community",
            "models": checks,
            "remote_writes": False,
            "scope": "read_only_handshake",
            "draft_write_validation": "NOT_TESTED",
        }
