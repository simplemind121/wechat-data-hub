"""Local collector for authorized exports or the official WeCom archive SDK.

Credentials stay in a private configuration file. This does not log into or inspect a WeChat client.
"""

import argparse
import hashlib
import json
import os
import re
import signal
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("UNSAFE_STATE_DIRECTORY")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)


def read_config(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("CONFIG_FILE_REQUIRED")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ValueError("CONFIG_REQUIRES_MODE_0600")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("token"), str):
        raise ValueError("INVALID_CONFIG")
    return value


class CollectorClient:
    def __init__(self, url: str, token: str, transport: httpx.BaseTransport | None = None):
        parts = urlsplit(url)
        if (
            parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
            or not parts.hostname
        ):
            raise ValueError("INVALID_HUB_URL")
        if parts.scheme != "https" and not (
            parts.scheme == "http"
            and parts.hostname in {"127.0.0.1", "localhost", "::1", "testserver"}
        ):
            raise ValueError("REMOTE_HUB_REQUIRES_HTTPS")
        self.client = httpx.Client(
            base_url=url.rstrip("/") + "/api/v1/collector/",
            headers={"Authorization": "Bearer " + token},
            timeout=120,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def status(self) -> dict[str, Any]:
        response = self.client.get("status")
        response.raise_for_status()
        return dict(response.json())

    def heartbeat(self, failure: str | None = None) -> None:
        response = self.client.post("heartbeat", json={"failure_code": failure})
        response.raise_for_status()

    def upload(self, path: Path, cursor: str) -> dict[str, Any]:
        with path.open("rb") as stream:
            response = self.client.post(
                "batches",
                data={"cursor": cursor},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
        response.raise_for_status()
        value = dict(response.json())
        if value.get("cursor") != cursor or not value.get("import_id"):
            raise ValueError("INVALID_ARCHIVE_RECEIPT")
        return value


def scan_files(
    client: CollectorClient, inbox: Path, state: Path, maximum: int = 1_073_741_824
) -> dict[str, int]:
    """Only copy regular, settled top-level exports. Inputs are never moved or deleted."""
    if inbox.is_symlink() or not inbox.is_dir():
        raise ValueError("INBOX_REQUIRED")
    private_directory(state)
    source = client.status()
    if source["kind"] != "personal_files":
        raise ValueError("SOURCE_KIND_MISMATCH")
    uploaded, skipped, failed = 0, 0, 0
    with sqlite3.connect(state / "receipts.db", timeout=30) as database:
        if os.name != "nt":
            (state / "receipts.db").chmod(0o600)
        database.execute(
            "CREATE TABLE IF NOT EXISTS receipts (source TEXT, sha TEXT, PRIMARY KEY(source,sha))"
        )
        for entry in sorted(inbox.iterdir()):
            if (
                entry.is_symlink()
                or not entry.is_file()
                or entry.suffix.lower() not in {".jsonl", ".json", ".csv", ".zip"}
                or entry.name == "manifest.json"
            ):
                continue
            try:
                before = entry.stat()
                if before.st_size > maximum:
                    raise ValueError("EXPORT_SIZE_LIMIT")
                with tempfile.TemporaryDirectory(prefix="snapshot-", dir=state) as temporary:
                    snapshot = Path(temporary) / entry.name
                    digest = hashlib.sha256()
                    count = 0
                    with entry.open("rb") as src, snapshot.open("xb") as dst:
                        while chunk := src.read(1_048_576):
                            count += len(chunk)
                            if count > maximum:
                                raise ValueError("EXPORT_SIZE_LIMIT")
                            digest.update(chunk)
                            dst.write(chunk)
                    after = entry.stat()
                    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ino,
                    ):
                        skipped += 1
                        continue
                    sha = digest.hexdigest()
                    if database.execute(
                        "SELECT 1 FROM receipts WHERE source=? AND sha=?", (source["id"], sha)
                    ).fetchone():
                        skipped += 1
                        continue
                    client.upload(snapshot, "file-" + sha)
                    database.execute(
                        "INSERT OR IGNORE INTO receipts VALUES (?,?)", (source["id"], sha)
                    )
                    database.commit()
                    uploaded += 1
            except (OSError, ValueError, httpx.HTTPError):
                failed += 1
    client.heartbeat("EXPORT_REJECTED" if failed else None)
    return {"archived_files": uploaded, "skipped_files": skipped, "failed_files": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["files", "wecom"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = read_config(args.config)
    client = CollectorClient(config["hub_url"], config["token"])
    stop = threading.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stop.set())
    try:
        while not stop.is_set():
            try:
                state = Path(config["state_directory"]).expanduser()
                if args.kind == "files":
                    result = scan_files(client, Path(config["inbox"]).expanduser(), state)
                else:
                    from wdh_api.wecom import sync_wecom

                    result = sync_wecom(client, config, state)
                partial = bool(result.get("failed_files"))
                print(json.dumps({"status": "partial" if partial else "ok", **result}), flush=True)
                if partial and args.once:
                    raise SystemExit(1)
            except Exception as exc:
                code = (
                    str(exc)
                    if isinstance(exc, ValueError) and re.fullmatch(r"[A-Z_]{1,80}", str(exc))
                    else "COLLECTOR_FAILED"
                )
                # HTTP/SDK errors can contain credentials or payloads; do not print them.
                reported = True
                try:
                    client.heartbeat(code)
                except Exception:
                    reported = False
                print(
                    json.dumps({"status": "failed", "code": code, "heartbeat_reported": reported}),
                    flush=True,
                )
                if args.once:
                    raise SystemExit(1) from None
            if args.once:
                break
            stop.wait(max(5, min(3600, int(config.get("poll_seconds", 15)))))
    finally:
        client.close()


if __name__ == "__main__":
    main()
