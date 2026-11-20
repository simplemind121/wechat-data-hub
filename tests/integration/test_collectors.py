"""Synthetic file and official archive protocol fixtures, not real account validation."""

import json
import zipfile

import httpx
import pytest
from wdh_api.collector import CollectorClient, scan_files
from wdh_api.wecom import archive_page, normalize_message, sync_wecom

from tests.integration.test_product import initialize
from tests.integration.test_sources import source


class Hub:
    def __init__(self):
        self.row = {"id": "fixture", "kind": "personal_files", "last_cursor": None}
        self.uploads = []

    def status(self):
        return self.row

    def upload(self, path, cursor):
        self.uploads.append((path.read_bytes(), cursor))
        self.row["last_cursor"] = cursor
        return {"import_id": "fixture", "cursor": cursor}

    def heartbeat(self, failure=None):
        pass


def test_files_are_immutable_restart_skips_and_does_not_follow_links(tmp_path):
    inbox, state = tmp_path / "inbox", tmp_path / "state"
    inbox.mkdir()
    data = b'{"synthetic":true}\n'
    (inbox / "messages.jsonl").write_bytes(data)
    (inbox / "partial.jsonl.part").write_text("unfinished")
    (inbox / "outside.jsonl").symlink_to(tmp_path / "private.jsonl")
    hub = Hub()
    assert scan_files(hub, inbox, state)["archived_files"] == 1
    assert scan_files(hub, inbox, state)["archived_files"] == 0
    assert (inbox / "messages.jsonl").read_bytes() == data
    hub.row["id"] = "different-source"
    assert scan_files(hub, inbox, state)["archived_files"] == 1


def test_one_rejected_export_does_not_block_other_files(tmp_path):
    inbox, state = tmp_path / "inbox", tmp_path / "state"
    inbox.mkdir()
    (inbox / "a.jsonl").write_bytes(b"rejected")
    (inbox / "b.jsonl").write_bytes(b"accepted")
    hub = Hub()
    original = hub.upload

    def upload(path, cursor):
        if path.read_bytes() == b"rejected":
            raise ValueError("REJECTED_FIXTURE")
        return original(path, cursor)

    hub.upload = upload
    result = scan_files(hub, inbox, state)
    assert result["archived_files"] == 1 and result["failed_files"] == 1


def test_collector_requires_https_and_does_not_follow_credential_redirects():
    with pytest.raises(ValueError, match="HTTPS"):
        CollectorClient("http://public.invalid", "synthetic")
    calls = []

    def redirect(request):
        calls.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://untrusted.invalid/"})

    client = CollectorClient(
        "https://synthetic.invalid", "synthetic", httpx.MockTransport(redirect)
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.status()
    assert calls == ["synthetic.invalid"]
    client.close()


class SDK:
    def __init__(self):
        self.pulls = []

    def pull(self, seq):
        self.pulls.append(seq)
        return {"chatdata": [{"seq": seq + 1, "publickey_ver": 1}]}

    def decrypt(self, record, path):
        return {
            "msgid": "synthetic-" + str(record["seq"]),
            "from": "员工",
            "tolist": ["客户"],
            "roomid": "合成群",
            "msgtime": 1795125600000,
            "msgtype": "text",
            "text": {"content": "M620 报价 3200元 😀"},
        }

    def media(self, fileid):
        return b"synthetic-media"


def test_wecom_real_ingest_and_cursor_retry_contract(product, tmp_path):
    client, _, worker = product
    initialize(client)
    created = source(client, "wecom_archive")
    token = created["token"]

    class Adapter:
        def __init__(self):
            self.lost_ack = True

        def status(self):
            return client.get(
                "/api/v1/collector/status", headers={"Authorization": "Bearer " + token}
            ).json()

        def upload(self, path, cursor):
            result = client.post(
                "/api/v1/collector/batches",
                headers={"Authorization": "Bearer " + token},
                files={"file": (path.name, path.read_bytes())},
                data={"cursor": cursor},
            )
            assert result.status_code == 202, result.text
            if self.lost_ack:
                self.lost_ack = False
                raise TimeoutError("synthetic response loss after commit")
            return result.json()

        def heartbeat(self):
            pass

    adapter, sdk = Adapter(), SDK()
    config = {"private_keys": {"1": "synthetic-not-a-real-key"}}
    with pytest.raises(TimeoutError):
        sync_wecom(adapter, config, tmp_path / "state", sdk)
    saved = (tmp_path / "state/pending.zip").read_bytes()
    assert sdk.pulls == [0]
    result = sync_wecom(adapter, config, tmp_path / "state", sdk)
    assert sdk.pulls == [0, 1]
    assert result["cursor"] == 2
    assert saved
    assert worker.run_once() and worker.run_once()
    messages = client.get("/api/v1/search?q=M620").json()["items"]
    assert len(messages) == 2
    coverage = client.get("/api/v1/imports").json()["items"]
    assert len(coverage) == 2


def test_wecom_rejects_missing_key_and_preserves_raw_unsupported_type(tmp_path):
    sdk = SDK()
    with pytest.raises(ValueError, match="KEY_VERSION"):
        archive_page(sdk, sdk.pull(0), {}, {}, tmp_path, 0)
    source_row = {
        "source_metadata": {
            "account_ref": "a",
            "device_ref": "d",
            "exporter_name": "wdh-wecom-finance",
            "exporter_version": "1.0.0",
            "data_format": "jsonl-v1",
            "platform": "other",
            "os_version": "unknown",
            "wechat_version": "unknown",
            "original_timezone": "Asia/Shanghai",
        }
    }
    path, cursor = archive_page(sdk, sdk.pull(0), source_row, {"1": "fixture"}, tmp_path, 0)
    assert cursor == 1
    with zipfile.ZipFile(path) as archive:
        row = json.loads(archive.read("messages.jsonl"))
        assert row["wecom_plaintext"]["text"]["content"].endswith("😀")
        assert row["wecom_envelope"]["seq"] == 1
    with pytest.raises(ValueError, match="MESSAGE_SCHEMA"):
        normalize_message({"msgid": "x", "tolist": [1]}, {})
