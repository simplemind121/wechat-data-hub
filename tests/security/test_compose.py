from pathlib import Path

import yaml


def test_default_deployment_binds_only_loopback_and_never_publishes_database() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())
    assert "ports" not in compose["services"]["db"]
    for name, service in compose["services"].items():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:")
        assert not service.get("privileged", False)
        assert all(mount.startswith("/") for mount in service.get("tmpfs", []))
        assert all("docker.sock" not in volume for volume in service.get("volumes", []))
        if name in ("api", "migrate", "web"):
            assert service["user"] != "0:0"
            assert service["read_only"]
            assert "ALL" in service["cap_drop"]


def test_down_keeps_volumes_and_base_images_are_digest_pinned() -> None:
    assert "down -v" not in Path("Makefile").read_text()
    for dockerfile in ("infra/api.Dockerfile", "infra/web.Dockerfile"):
        for line in Path(dockerfile).read_text().splitlines():
            if line.startswith("FROM "):
                assert "@sha256:" in line
