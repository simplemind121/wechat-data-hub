"""Immutable local CAS. The private root must be owned exclusively by the service account."""

import hashlib
import os
import re
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO


class StorageError(ValueError):
    """Stable error code; deliberately omits source paths and private payloads."""


@dataclass(frozen=True)
class Blob:
    sha256: str
    byte_size: int
    cas_key: str


class ContentStore:
    def __init__(self, root: Path, max_bytes: int = 1_073_741_824) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.root = root.absolute()
        self.max_bytes = max_bytes
        self._directory(self.root)
        self._directory(self.root / ".staging")
        self._directory(self.root / "sha256")

    @staticmethod
    def _directory(path: Path) -> None:
        # Reject symlinks in ALL ancestors, not only the leaf. The root is private and trusted.
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise StorageError("UNSAFE_PATH")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.is_dir():
            raise StorageError("UNSAFE_PATH")

    def _path(self, digest: str) -> Path:
        if not re.fullmatch("[a-f0-9]{64}", digest):
            raise StorageError("INVALID_HASH")
        directory = self.root / "sha256" / digest[:2]
        self._directory(directory)
        return directory / digest

    @staticmethod
    def _verify(path: Path, digest: str) -> None:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise StorageError("UNSAFE_PATH")
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as exc:
            raise StorageError("UNSAFE_PATH") from exc
        if actual != digest:
            raise StorageError("HASH_MISMATCH")

    def put(self, stream: BinaryIO) -> Blob:
        self._directory(self.root / ".staging")
        fd, temporary = tempfile.mkstemp(dir=self.root / ".staging")
        staged = Path(temporary)
        try:
            digest = hashlib.sha256()
            count = 0
            with os.fdopen(fd, "wb") as destination:
                while chunk := stream.read(1024 * 1024):
                    count += len(chunk)
                    if count > self.max_bytes:
                        raise StorageError("SIZE_LIMIT")
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
                os.fchmod(destination.fileno(), 0o400)
            value = digest.hexdigest()
            target = self._path(value)
            try:
                # link is atomic and never replaces a pre-existing file, unlike os.replace.
                os.link(staged, target)
            except FileExistsError:
                self._verify(target, value)
            directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return Blob(value, count, str(target.relative_to(self.root)))
        finally:
            staged.unlink(missing_ok=True)

    def read(self, digest: str) -> bytes:
        path = self._path(digest)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                data = stream.read(self.max_bytes + 1)
        except OSError as exc:
            raise StorageError("OBJECT_UNAVAILABLE") from exc
        if len(data) > self.max_bytes:
            raise StorageError("SIZE_LIMIT")
        if hashlib.sha256(data).hexdigest() != digest:
            raise StorageError("HASH_MISMATCH")
        return data


def validate_archive(
    stream: BinaryIO,
    *,
    max_files: int = 5000,
    max_total_bytes: int = 1_073_741_824,
    max_ratio: int = 100,
) -> list[str]:
    """Inspect ZIP metadata only; this function NEVER extracts files or trusts their MIME."""
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > max_files:
                raise StorageError("FILE_COUNT_LIMIT")
            total = 0
            paths: set[str] = set()
            for entry in entries:
                name = entry.filename
                path = PurePosixPath(name)
                if (
                    not name
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or ":" in name
                    or "\x00" in name
                ):
                    raise StorageError("UNSAFE_ARCHIVE_PATH")
                normalized = str(path)
                if normalized in paths:
                    raise StorageError("DUPLICATE_ARCHIVE_PATH")
                paths.add(normalized)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise StorageError("UNSAFE_ARCHIVE_ENTRY")
                if entry.flag_bits & 1:
                    raise StorageError("ENCRYPTED_ARCHIVE_UNSUPPORTED")
                total += entry.file_size
                if total > max_total_bytes:
                    raise StorageError("SIZE_LIMIT")
                if entry.file_size > max(1, entry.compress_size) * max_ratio:
                    raise StorageError("COMPRESSION_RATIO_LIMIT")
            return sorted(paths)
    except (zipfile.BadZipFile, NotImplementedError) as exc:
        raise StorageError("INVALID_ARCHIVE") from exc
