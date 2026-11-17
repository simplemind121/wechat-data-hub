"""Streaming authenticated backups and restore into a new database and a new directory only."""

import hashlib
import io
import json
import os
import secrets
import struct
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from alembic import command
from alembic.config import Config
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import DateTime, false, inspect, select
from sqlalchemy.engine import Engine
from wdh_domain.models import (
    Base,
    LoginSession,
    LoginThrottle,
    Membership,
    SetupLock,
    SourceBlob,
    User,
    Workspace,
)
from wdh_storage.cas import ContentStore

from wdh_api.config import Settings, get_settings
from wdh_api.db import make_engine

MAGIC = b"WDHBK02\n"
MAX_FRAME = 1024 * 1024


def key_for(password: str, salt: bytes) -> bytes:
    if len(password) < 16:
        raise ValueError("BACKUP_PASSWORD_MIN_16")
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)


class EncryptedWriter:
    def __init__(self, stream: BinaryIO, password: str) -> None:
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(8)
        self.header = MAGIC + salt + nonce
        self.cipher = AESGCM(key_for(password, salt))
        self.nonce, self.counter, self.stream = nonce, 0, stream
        stream.write(self.header)

    def write(self, data: bytes) -> int:
        for offset in range(0, len(data), MAX_FRAME):
            counter = self.counter.to_bytes(4, "big")
            encrypted = self.cipher.encrypt(
                self.nonce + counter,
                data[offset : offset + MAX_FRAME],
                self.header + counter + b"DATA",
            )
            self.stream.write(struct.pack(">I", len(encrypted)) + encrypted)
            self.counter += 1
        return len(data)

    def finish(self) -> None:
        counter = self.counter.to_bytes(4, "big")
        self.stream.write(
            b"\0\0\0\0"
            + self.cipher.encrypt(self.nonce + counter, b"", self.header + counter + b"END")
        )
        self.stream.flush()


class EncryptedReader:
    def __init__(self, stream: BinaryIO, password: str) -> None:
        self.header = stream.read(len(MAGIC) + 24)
        if len(self.header) != len(MAGIC) + 24 or not self.header.startswith(MAGIC):
            raise ValueError("INVALID_BACKUP_HEADER")
        self.cipher = AESGCM(key_for(password, self.header[len(MAGIC) : len(MAGIC) + 16]))
        self.nonce = self.header[-8:]
        self.stream, self.counter, self.buffer, self.ended = stream, 0, b"", False

    def frame(self) -> bytes:
        length = self.stream.read(4)
        if len(length) != 4:
            raise ValueError("TRUNCATED_BACKUP")
        size = struct.unpack(">I", length)[0]
        if size > MAX_FRAME + 16:
            raise ValueError("INVALID_BACKUP_FRAME")
        data = self.stream.read(size or 16)
        counter = self.counter.to_bytes(4, "big")
        try:
            result = self.cipher.decrypt(
                self.nonce + counter, data, self.header + counter + (b"DATA" if size else b"END")
            )
        except InvalidTag as exc:
            raise ValueError("BACKUP_AUTHENTICATION_FAILED") from exc
        self.counter += 1
        if not size:
            self.ended = True
            if result or self.stream.read(1):
                raise ValueError("INVALID_BACKUP_END")
        return result

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise ValueError("STREAMING_READ_SIZE_REQUIRED")
        while len(self.buffer) < size and not self.ended:
            self.buffer += self.frame()
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def finish(self) -> None:
        while not self.ended:
            self.frame()


def add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mode = len(data), 0o600
    archive.addfile(info, io.BytesIO(data))


def backup_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def create_backup(
    engine: Engine,
    store: ContentStore,
    destination: Path,
    password: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """A repeatable-read database snapshot plus immutable originals; output is exclusive 0600."""
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    objects: set[str] = set()
    with destination.open("xb") as output:
        os.chmod(destination, 0o600)
        encrypted = EncryptedWriter(output, password)
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection = connection.execution_options(isolation_level="REPEATABLE READ")
            with connection.begin():
                if engine.dialect.name == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                version = connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version"
                ).scalar_one()
                with tarfile.open(fileobj=cast(BinaryIO, encrypted), mode="w|") as archive:
                    for table in Base.metadata.sorted_tables:
                        # Spool one table to disk in the private data directory, bounded in RAM.
                        import tempfile

                        with tempfile.TemporaryFile(dir=store.root) as staging:
                            count = 0
                            query = select(table)
                            if workspace_id is not None:
                                if "workspace_id" in table.c:
                                    query = query.where(table.c.workspace_id == workspace_id)
                                elif table.name == Workspace.__tablename__:
                                    query = query.where(table.c.id == workspace_id)
                                elif table.name == User.__tablename__:
                                    query = query.where(
                                        table.c.id.in_(
                                            select(Membership.user_id).where(
                                                Membership.workspace_id == workspace_id
                                            )
                                        )
                                    )
                                elif table.name == LoginThrottle.__tablename__:
                                    query = query.where(false())
                            for row in connection.execute(query.execution_options(yield_per=500)):
                                record = dict(row._mapping)
                                staging.write(
                                    (
                                        json.dumps(record, ensure_ascii=False, default=str) + "\n"
                                    ).encode()
                                )
                                count += 1
                                if table.name == SourceBlob.__tablename__:
                                    objects.add(record["sha256"])
                            info = tarfile.TarInfo(f"database/{table.name}.jsonl")
                            info.size, info.mode = staging.tell(), 0o600
                            staging.seek(0)
                            archive.addfile(info, staging)
                            counts[table.name] = count
                    for digest in sorted(objects):
                        with store.open(digest) as stream:
                            info = tarfile.TarInfo(f"objects/{digest}")
                            info.size, info.mode = os.fstat(stream.fileno()).st_size, 0o400
                            archive.addfile(info, stream)
                    metadata = {
                        "version": version,
                        "counts": counts,
                        "objects": len(objects),
                        "format": "WDHBK02",
                        "scope": "workspace" if workspace_id else "system",
                        "configuration": {
                            "providers": "disabled",
                            "credentials": "recreate .env; core credentials are database hashes",
                        },
                    }
                    add_bytes(archive, "manifest.json", json.dumps(metadata).encode())
        encrypted.finish()
        os.fsync(output.fileno())
    return {
        "counts": counts,
        "objects": len(objects),
        "sha256": backup_digest(destination),
    }


def restore_backup(source: Path, password: str, target: Settings) -> dict[str, Any]:
    """Fail closed on any existing destination. No production table clearing or downgrade."""
    if target.data_root.exists():
        raise ValueError("RESTORE_DIRECTORY_MUST_BE_NEW")
    engine = make_engine(target)
    try:
        if inspect(engine).get_table_names():
            raise ValueError("RESTORE_DATABASE_MUST_BE_EMPTY")
        target.data_root.mkdir(parents=True, mode=0o700)
        store = ContentStore(target.data_root, target.import_max_bytes)
        staging = target.data_root / "restore-staging"
        staging.mkdir(mode=0o700)
        expected_tables = {table.name for table in Base.metadata.sorted_tables}
        tables: dict[str, Path] = {}
        objects: set[str] = set()
        metadata: dict[str, Any] | None = None
        with source.open("rb") as stream:
            decrypted = EncryptedReader(stream, password)
            with tarfile.open(fileobj=cast(BinaryIO, decrypted), mode="r|") as archive:
                for info in archive:
                    if not info.isfile():
                        raise ValueError("UNSAFE_BACKUP_ENTRY")
                    data = archive.extractfile(info)
                    if data is None:
                        raise ValueError("INVALID_BACKUP_ENTRY")
                    if info.name == "manifest.json":
                        if metadata is not None or info.size > 1_048_576:
                            raise ValueError("INVALID_BACKUP_MANIFEST")
                        metadata = json.loads(data.read())
                    elif info.name.startswith("objects/"):
                        digest = info.name.removeprefix("objects/")
                        if len(digest) != 64 or any(c not in "abcdef0123456789" for c in digest):
                            raise ValueError("INVALID_OBJECT_NAME")
                        blob = store.put(cast(BinaryIO, data))
                        if blob.sha256 != digest or digest in objects:
                            raise ValueError("OBJECT_HASH_MISMATCH")
                        objects.add(digest)
                    elif info.name.startswith("database/") and info.name.endswith(".jsonl"):
                        name = info.name.removeprefix("database/").removesuffix(".jsonl")
                        if name not in expected_tables or name in tables:
                            raise ValueError("INVALID_BACKUP_TABLE")
                        path = staging / (name + ".jsonl")
                        with path.open("xb") as output:
                            os.chmod(path, 0o600)
                            while chunk := data.read(1024 * 1024):
                                output.write(chunk)
                        tables[name] = path
                    else:
                        raise ValueError("UNSAFE_BACKUP_PATH")
            decrypted.finish()
        from wdh_api.main import SCHEMA_REVISION

        if (
            not metadata
            or metadata.get("version") != SCHEMA_REVISION
            or set(tables) != expected_tables
        ):
            raise ValueError("BACKUP_SCHEMA_MISMATCH")
        if metadata.get("objects") != len(objects):
            raise ValueError("BACKUP_OBJECT_COUNT_MISMATCH")
        previous = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = target.database_url
            get_settings.cache_clear()
            command.upgrade(Config("alembic.ini"), "head")
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous
            get_settings.cache_clear()
        restored: dict[str, int] = {}
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                # Initialization seed is replaced only in the verified-empty NEW destination.
                if table.name == SetupLock.__tablename__:
                    connection.execute(table.delete())
                count = 0
                insert_rows: list[dict[str, Any]] = []
                with tables[table.name].open() as records:
                    for line in records:
                        row = json.loads(line)
                        count += 1
                        if table.name == LoginSession.__tablename__:
                            continue  # Recovered users log in again; old sessions stay invalid.
                        for column in table.columns:
                            if (
                                isinstance(column.type, DateTime)
                                and row.get(column.name) is not None
                            ):
                                row[column.name] = datetime.fromisoformat(row[column.name])
                        if table.name == SourceBlob.__tablename__ and row["sha256"] not in objects:
                            raise ValueError("MISSING_BACKUP_OBJECT")
                        insert_rows.append(row)
                        if len(insert_rows) >= 500:
                            connection.execute(table.insert(), insert_rows)
                            insert_rows = []
                    if insert_rows:
                        connection.execute(table.insert(), insert_rows)
                if count != metadata["counts"][table.name]:
                    raise ValueError("BACKUP_TABLE_COUNT_MISMATCH")
                restored[table.name] = 0 if table.name == LoginSession.__tablename__ else count
        for path in tables.values():
            path.unlink()
        staging.rmdir()
        return {
            "counts": restored,
            "source_counts": metadata["counts"],
            "objects": len(objects),
            "sessions_invalidated": True,
        }
    finally:
        engine.dispose()
