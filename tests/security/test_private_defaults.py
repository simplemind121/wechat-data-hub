from fastapi.testclient import TestClient
from wdh_api.config import Settings
from wdh_api.main import create_app


def test_errors_do_not_echo_malicious_input_or_paths() -> None:
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/v1/unknown?password=secret&body=<script>alert(1)</script>")
        assert response.status_code == 401
        assert "secret" not in response.text
        assert "<script>" not in response.text
        assert response.headers["Cache-Control"] == "no-store"


def test_every_data_endpoint_rejects_anonymous_requests() -> None:
    paths = create_app(Settings(_env_file=None)).openapi()["paths"]
    public = {
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/auth/login",
        "/api/v1/auth/setup",
        "/api/v1/auth/status",
    }
    with TestClient(create_app(Settings(_env_file=None))) as client:
        for path, methods in paths.items():
            if path in public:
                continue
            for method in methods:
                url = path.replace("{batch_id}", "00000000-0000-0000-0000-000000000000")
                response = client.request(method, url)
                assert response.status_code == 401, (method, path)
