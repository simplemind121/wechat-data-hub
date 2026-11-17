import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from wdh_storage.cas import ContentStore, StorageError, validate_archive


def test_preserves_exact_bytes_and_is_idempotent_under_concurrent_writes(tmp_path: Path) -> None:
    store = ContentStore(tmp_path / "cas", max_bytes=100)
    raw = "中文🧪\r\n\x00".encode()
    with ThreadPoolExecutor(max_workers=8) as executor:
        blobs = list(executor.map(lambda _: store.put(io.BytesIO(raw)), range(16)))
    assert len({blob.sha256 for blob in blobs}) == 1
    blob = blobs[0]
    assert store.read(blob.sha256) == raw
    assert blob.byte_size == len(raw)
    path = tmp_path / "cas" / blob.cas_key
    assert path.stat().st_mode & 0o222 == 0
    assert len(list((tmp_path / "cas" / "sha256").rglob(blob.sha256))) == 1
    assert list((tmp_path / "cas" / ".staging").iterdir()) == []


def test_oversized_stream_is_rejected_without_partial_archive(tmp_path: Path) -> None:
    store = ContentStore(tmp_path / "cas", max_bytes=4)
    with pytest.raises(StorageError, match="SIZE_LIMIT"):
        store.put(io.BytesIO(b"12345"))
    assert not list((tmp_path / "cas" / "sha256").rglob("?" * 64))
    assert list((tmp_path / "cas" / ".staging").iterdir()) == []


@pytest.mark.parametrize("key", ["../secret", "/etc/passwd", "x" * 64, "a" * 63, "a" * 65])
def test_raw_paths_cannot_be_used_as_blob_keys(tmp_path: Path, key: str) -> None:
    store = ContentStore(tmp_path / "cas")
    with pytest.raises(StorageError, match="INVALID_HASH"):
        store.read(key)


def test_symlink_root_and_symlink_blob_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "private"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(StorageError, match="UNSAFE_PATH"):
        ContentStore(link)
    store = ContentStore(tmp_path / "cas")
    blob = store.put(io.BytesIO(b"original"))
    blob_path = tmp_path / "cas" / blob.cas_key
    blob_path.unlink()
    secret = tmp_path / "secret"
    secret.write_bytes(b"secret")
    blob_path.symlink_to(secret)
    with pytest.raises(StorageError):
        store.read(blob.sha256)
    with pytest.raises(StorageError):
        store.put(io.BytesIO(b"original"))
    assert secret.read_bytes() == b"secret"


def test_corrupted_existing_object_is_never_overwritten(tmp_path: Path) -> None:
    store = ContentStore(tmp_path / "cas")
    blob = store.put(io.BytesIO(b"original"))
    blob_path = tmp_path / "cas" / blob.cas_key
    os.chmod(blob_path, 0o600)
    blob_path.write_bytes(b"corrupted")
    with pytest.raises(StorageError, match="HASH_MISMATCH"):
        store.put(io.BytesIO(b"original"))
    assert blob_path.read_bytes() == b"corrupted"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/windows", "foo\\bar", "a/../b"])
def test_archive_paths_are_untrusted(name: str) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, b"synthetic")
    buffer.seek(0)
    with pytest.raises(StorageError, match="UNSAFE_ARCHIVE_PATH"):
        validate_archive(buffer)


def test_archive_symlink_and_bomb_rejected() -> None:
    for symlink in (True, False):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            entry = zipfile.ZipInfo("payload")
            entry.create_system = 3
            entry.external_attr = (0o120777 if symlink else 0o100600) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, b"../../secret" if symlink else b"0" * 100_000)
        buffer.seek(0)
        with pytest.raises(StorageError):
            validate_archive(buffer)


def test_valid_archive_inspected_without_extracting(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("media/a.txt", "合成🧪")
    buffer.seek(0)
    assert validate_archive(buffer) == ["media/a.txt"]
    assert list(tmp_path.iterdir()) == []
