import hashlib
import io
import json
import shutil
import zipfile
from pathlib import PurePosixPath
from typing import Any, BinaryIO, cast

from sqlalchemy import select
from sqlalchemy.orm import Session
from wdh_adapters.files import ADAPTER_VERSION, Manifest, safe_path
from wdh_domain.models import Account, Device, IngestBatch, Job, SourceBlob, Workspace
from wdh_storage.cas import Blob, ContentStore, validate_archive

from wdh_api.security import ApiError, Principal, audit


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()


def register_blob(session: Session, workspace_id: str, blob: Blob) -> SourceBlob:
    current = session.scalar(
        select(SourceBlob).where(
            SourceBlob.workspace_id == workspace_id, SourceBlob.sha256 == blob.sha256
        )
    )
    if not current:
        current = SourceBlob(
            workspace_id=workspace_id,
            sha256=blob.sha256,
            byte_size=blob.byte_size,
            cas_key=blob.cas_key,
        )
        session.add(current)
        session.flush()
    return current


def accept_upload(
    session: Session,
    store: ContentStore,
    who: Principal,
    stream: BinaryIO,
    manifest_bytes: bytes | None,
    filename: str,
    max_files: int,
    max_bytes: int,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    main = store.put(stream)
    session.scalar(select(Workspace).where(Workspace.id == who.workspace_id).with_for_update())
    # Originals remain tracked even if subsequent source validation is rejected.
    main_blob = register_blob(session, who.workspace_id, main)
    session.commit()
    files: dict[str, Blob] = {}
    if source_metadata is not None:
        # A user-declared wrapper: actual byte size/hash are computed here, never guessed in the UI.
        metadata = {
            key: value
            for key, value in source_metadata.items()
            if key
            in {
                "account_ref",
                "device_ref",
                "platform",
                "os_version",
                "wechat_version",
                "exporter_name",
                "exporter_version",
                "exported_at",
                "original_timezone",
                "data_format",
                "field_mapping",
                "json_root",
                "delimiter",
                "coverage_notes",
            }
        }
        generated = {
            "schema_version": "1.0.0",
            "export_id": "user-declared-upload-" + main.sha256[:32],
            "os_version": "unknown",
            "wechat_version": "unknown",
            "exporter_name": "unknown",
            "exporter_version": "unknown",
            "media_base_path": "media",
            "consent_scope": "user-declared-authorized-export",
            "coverage_notes": "用户声明来源信息，源端完整性未验证；哈希由本系统实算。",
            **metadata,
            "payload_files": [
                {
                    "path": PurePosixPath(filename).name,
                    "size_bytes": main.byte_size,
                    "sha256": main.sha256,
                }
            ],
        }
        manifest_bytes = json.dumps(generated, ensure_ascii=False).encode()
    if manifest_bytes is None:
        with store.open(main.sha256) as archived:
            names = validate_archive(archived, max_files=max_files, max_total_bytes=max_bytes)
            manifests = [name for name in names if PurePosixPath(name).name == "manifest.json"]
            if len(manifests) != 1:
                raise ApiError(400, "MANIFEST_REQUIRED", "ZIP 中需且仅需一份 manifest.json")
            root = PurePosixPath(manifests[0]).parent
            with zipfile.ZipFile(archived) as archive:
                expanded = sum(info.file_size for info in archive.infolist())
                if expanded * 3 + 33_554_432 > shutil.disk_usage(store.root).free:
                    raise ApiError(
                        507, "INSUFFICIENT_STORAGE", "ZIP 展开后的空间不足，请扩容后导入"
                    )
                entry = archive.getinfo(manifests[0])
                if entry.file_size > 1_048_576:
                    raise ApiError(400, "MANIFEST_TOO_LARGE", "导入清单过大")
                manifest_bytes = archive.read(entry)
                manifest = Manifest.model_validate_json(manifest_bytes)
                total = 0
                for name in names:
                    info = archive.getinfo(name)
                    if info.is_dir():
                        continue
                    try:
                        relative = safe_path(str(PurePosixPath(name).relative_to(root)))
                    except ValueError as exc:
                        raise ApiError(
                            400, "ARCHIVE_ROOT_MISMATCH", "ZIP 文件需位于清单同一目录内"
                        ) from exc
                    with archive.open(info) as item:
                        blob = store.put(cast(BinaryIO, item))
                    total += blob.byte_size
                    if total > max_bytes:
                        raise ApiError(413, "SIZE_LIMIT", "解压内容超出限制")
                    files[relative] = blob
    else:
        manifest = Manifest.model_validate_json(manifest_bytes)
        if len(manifest.payload_files) != 1:
            raise ApiError(400, "USE_ZIP", "多数据文件或媒体请使用 ZIP 导入")
        if PurePosixPath(manifest.payload_files[0].path).name != PurePosixPath(filename).name:
            raise ApiError(400, "PAYLOAD_NAME_MISMATCH", "所选文件与清单文件名不一致")
        files[manifest.payload_files[0].path] = main
    manifest_blob = store.put(io.BytesIO(manifest_bytes))
    session.scalar(select(Workspace).where(Workspace.id == who.workspace_id).with_for_update())
    register_blob(session, who.workspace_id, manifest_blob)
    for payload in manifest.payload_files:
        found = files.get(payload.path)
        if not found or found.sha256 != payload.sha256 or found.byte_size != payload.size_bytes:
            raise ApiError(
                400, "PAYLOAD_CHECKSUM_MISMATCH", "数据文件缺失，或大小/SHA-256 与清单不符"
            )
    adapter_id = manifest.data_format
    adapter_version = (
        ADAPTER_VERSION
        + "+cfg."
        + fingerprint(
            {
                "mapping": manifest.field_mapping,
                "timezone": manifest.original_timezone,
                "root": manifest.json_root,
                "delimiter": manifest.delimiter,
            }
        )[:12]
    )
    existing = session.scalar(
        select(IngestBatch).where(
            IngestBatch.workspace_id == who.workspace_id,
            IngestBatch.main_blob_id == main_blob.id,
            IngestBatch.adapter_id == adapter_id,
            IngestBatch.adapter_version == adapter_version,
        )
    )
    if existing:
        if any(
            existing.manifest.get(key) != getattr(manifest, key)
            for key in ("account_ref", "device_ref", "exporter_name", "exporter_version")
        ):
            raise ApiError(
                409,
                "SOURCE_METADATA_CONFLICT",
                "原始文件已归档，来源元数据不同，请使用含清单的 ZIP",
            )
        job = session.scalar(
            select(Job).where(
                Job.workspace_id == who.workspace_id,
                Job.batch_id == existing.id,
                Job.kind == "ingest",
            )
        )
        return {
            "import_id": existing.id,
            "job_id": job.id if job else None,
            "status": "already_ingested",
        }
    account = session.scalar(
        select(Account).where(
            Account.workspace_id == who.workspace_id, Account.account_ref == manifest.account_ref
        )
    )
    if not account:
        account = Account(workspace_id=who.workspace_id, account_ref=manifest.account_ref)
        session.add(account)
        session.flush()
    device = session.scalar(
        select(Device).where(
            Device.workspace_id == who.workspace_id, Device.device_ref == manifest.device_ref
        )
    )
    if device and device.account_id != account.id:
        raise ApiError(409, "DEVICE_ACCOUNT_CONFLICT", "设备标识已属于其他账号，请使用不同来源标识")
    if not device:
        device = Device(
            workspace_id=who.workspace_id,
            account_id=account.id,
            device_ref=manifest.device_ref,
            platform=manifest.platform,
            os_version=manifest.os_version,
            wechat_version=manifest.wechat_version,
        )
        session.add(device)
        session.flush()
    for blob in files.values():
        register_blob(session, who.workspace_id, blob)
    data = manifest.model_dump(mode="json")
    data["manifest_origin"] = (
        "user-declared-generated" if source_metadata is not None else "supplied"
    )
    data["_archive"] = {
        "manifest_sha256": manifest_blob.sha256,
        "files": {
            path: {"sha256": blob.sha256, "byte_size": blob.byte_size}
            for path, blob in files.items()
        },
    }
    batch = IngestBatch(
        workspace_id=who.workspace_id,
        account_id=account.id,
        device_id=device.id,
        main_blob_id=main_blob.id,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        manifest=data,
        original_timezone=manifest.original_timezone,
        batch_status="archived",
    )
    session.add(batch)
    session.flush()
    job = Job(
        workspace_id=who.workspace_id,
        kind="ingest",
        batch_id=batch.id,
        idempotency_key=batch.id,
        payload={"actor_id": who.user_id},
    )
    session.add(job)
    session.flush()
    audit(session, who, "import.archived", batch.id)
    session.commit()
    return {"import_id": batch.id, "job_id": job.id, "status": "queued"}


def sniff(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"fLaC"):
        return "audio/flac"
    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    return "application/octet-stream"
