from fastapi.testclient import TestClient
from wdh_api.config import Settings
from wdh_api.main import create_app


def test_errors_do_not_echo_malicious_input_or_paths() -> None:
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/v1/unknown?password=secret&body=<script>alert(1)</script>")
        assert response.status_code == 404
        assert "secret" not in response.text
        assert "<script>" not in response.text
        assert response.headers["Cache-Control"] == "no-store"


def test_no_data_or_mutation_endpoints_exposed_before_authentication_exists() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]
    assert set(paths) == {"/api/v1/health/live", "/api/v1/health/ready"}
    assert all(set(methods) == {"get"} for methods in paths.values())
