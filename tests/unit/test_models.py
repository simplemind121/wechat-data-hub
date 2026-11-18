import hashlib
import io
import tarfile
from contextlib import contextmanager

import pytest
from wdh_api import models
from wdh_api.config import Settings


def fixture_archive(monkeypatch, unsafe=False, bad_hash=False):
    content = b"synthetic native runtime"
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as archive:
        info = tarfile.TarInfo("../escape" if unsafe else "package/llama-server")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    data = packed.getvalue()
    spec = {
        "url": "https://github.com/synthetic-only",
        "format": "tar.gz",
        "archive_bytes": len(data),
        "archive_sha256": hashlib.sha256(data).hexdigest(),
        "files": [
            {
                "name": "llama-server",
                "bytes": len(content),
                "sha256": "0" * 64 if bad_hash else hashlib.sha256(content).hexdigest(),
                "executable": True,
            }
        ],
    }
    monkeypatch.setattr(models, "catalog", lambda: {"runtime": spec})

    @contextmanager
    def download(url):
        yield io.BytesIO(data)

    monkeypatch.setattr(models, "download", download)


def test_model_install_checks_hash_and_repeat_is_no_network_write(tmp_path, monkeypatch):
    fixture_archive(monkeypatch)
    settings = Settings(_env_file=None, data_root=tmp_path)
    assert models.install("runtime", settings)["status"] == "installed"
    file = tmp_path / "models/runtime/llama-server"
    assert file.stat().st_mode & 0o100
    before = file.stat().st_mtime_ns
    assert models.install("runtime", settings)["status"] == "already_installed"
    assert file.stat().st_mtime_ns == before


@pytest.mark.parametrize("unsafe,bad_hash", [(True, False), (False, True)])
def test_model_archive_traversal_or_hash_mismatch_never_commits(
    tmp_path, monkeypatch, unsafe, bad_hash
):
    fixture_archive(monkeypatch, unsafe, bad_hash)
    with pytest.raises(ValueError, match="UNSAFE_MODEL_ARCHIVE|MODEL_HASH_MISMATCH"):
        models.install("runtime", Settings(_env_file=None, data_root=tmp_path))
    assert not (tmp_path / "models/runtime/llama-server").exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://github.com/model", "https://evil.example/model"]
)
def test_installer_rejects_non_catalog_scheme_or_host_before_request(url):
    with pytest.raises(ValueError, match="UNTRUSTED_MODEL_SOURCE"):
        with models.download(url):
            pass


def test_heavy_model_slot_rejects_concurrent_load_without_corrupting_lock(tmp_path):
    import pytest
    from wdh_api.processing import ModelBusy, model_slot

    with model_slot(tmp_path, "llm"):
        with pytest.raises(ModelBusy):
            with model_slot(tmp_path, "llm"):
                pass
        with model_slot(tmp_path, "embedding"):
            pass
    with model_slot(tmp_path, "llm"):
        pass
