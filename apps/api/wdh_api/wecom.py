"""Official WeCom Finance C ABI connector. No personal-client extraction code.

The administrator supplies the official shared library and their enterprise archive private keys.
"""

import base64
import ctypes as ct
import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from wdh_api.collector import CollectorClient, private_directory


class FinanceSDK:
    def __init__(self, path: Path, corp_id: str, secret: str):
        if path.is_symlink() or not path.is_absolute() or not path.is_file():
            raise ValueError("OFFICIAL_SDK_REQUIRED")
        self.lib = ct.CDLL(str(path))
        signatures = {
            "NewSdk": (ct.c_void_p, []),
            "Init": (ct.c_int, [ct.c_void_p, ct.c_char_p, ct.c_char_p]),
            "DestroySdk": (None, [ct.c_void_p]),
            "NewSlice": (ct.c_void_p, []),
            "FreeSlice": (None, [ct.c_void_p]),
            "GetChatData": (
                ct.c_int,
                [
                    ct.c_void_p,
                    ct.c_ulonglong,
                    ct.c_uint,
                    ct.c_char_p,
                    ct.c_char_p,
                    ct.c_int,
                    ct.c_void_p,
                ],
            ),
            "GetContentFromSlice": (ct.c_void_p, [ct.c_void_p]),
            "GetSliceLen": (ct.c_int, [ct.c_void_p]),
            "DecryptData": (ct.c_int, [ct.c_char_p, ct.c_char_p, ct.c_void_p]),
            "NewMediaData": (ct.c_void_p, []),
            "FreeMediaData": (None, [ct.c_void_p]),
            "GetMediaData": (
                ct.c_int,
                [
                    ct.c_void_p,
                    ct.c_char_p,
                    ct.c_char_p,
                    ct.c_char_p,
                    ct.c_char_p,
                    ct.c_int,
                    ct.c_void_p,
                ],
            ),
            "GetData": (ct.c_void_p, [ct.c_void_p]),
            "GetDataLen": (ct.c_int, [ct.c_void_p]),
            "GetOutIndexBuf": (ct.c_char_p, [ct.c_void_p]),
            "IsMediaDataFinish": (ct.c_int, [ct.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, arguments
        self.handle = self.lib.NewSdk()
        if not self.handle:
            raise ValueError("WECOM_SDK_INIT_FAILED")
        if self.lib.Init(self.handle, corp_id.encode(), secret.encode()) != 0:
            self.close()
            raise ValueError("WECOM_SDK_INIT_FAILED")

    def close(self) -> None:
        if self.handle:
            self.lib.DestroySdk(self.handle)
            self.handle = None

    def _slice(self, function: Any, *args: Any) -> dict[str, Any]:
        result = self.lib.NewSlice()
        if not result:
            raise ValueError("WECOM_SDK_ALLOCATION_FAILED")
        try:
            if function(*args, result) != 0:
                raise ValueError("WECOM_SDK_REQUEST_FAILED")
            size = self.lib.GetSliceLen(result)
            if not 0 < size <= 16_777_216:
                raise ValueError("WECOM_RESPONSE_LIMIT")
            value = json.loads(ct.string_at(self.lib.GetContentFromSlice(result), size))
            if not isinstance(value, dict) or value.get("errcode", 0) != 0:
                raise ValueError("WECOM_API_REJECTED")
            return value
        finally:
            self.lib.FreeSlice(result)

    def pull(self, seq: int) -> dict[str, Any]:
        return self._slice(self.lib.GetChatData, self.handle, seq, 100, b"", b"", 10)

    def decrypt(self, record: dict[str, Any], private_key: Path) -> dict[str, Any]:
        if private_key.is_symlink() or (os.name != "nt" and private_key.stat().st_mode & 0o077):
            raise ValueError("WECOM_PRIVATE_KEY_PERMISSIONS")
        key = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("WECOM_RSA_KEY_REQUIRED")
        # This is the enterprise's own official archive envelope, not a WeChat database key.
        random_key = key.decrypt(
            base64.b64decode(record["encrypt_random_key"], validate=True), padding.PKCS1v15()
        )
        return self._slice(
            self.lib.DecryptData, random_key, str(record["encrypt_chat_msg"]).encode()
        )

    def media(self, file_id: str, maximum: int = 33_554_432) -> bytes:
        result, index = bytearray(), b""
        for _ in range(2048):
            piece = self.lib.NewMediaData()
            if not piece:
                raise ValueError("WECOM_SDK_ALLOCATION_FAILED")
            try:
                if (
                    self.lib.GetMediaData(self.handle, index, file_id.encode(), b"", b"", 10, piece)
                    != 0
                ):
                    raise ValueError("WECOM_MEDIA_FAILED")
                size = self.lib.GetDataLen(piece)
                if size < 0 or len(result) + size > maximum:
                    raise ValueError("WECOM_MEDIA_LIMIT")
                result.extend(ct.string_at(self.lib.GetData(piece), size))
                if self.lib.IsMediaDataFinish(piece):
                    return bytes(result)
                next_index = self.lib.GetOutIndexBuf(piece)
                if not next_index or next_index == index:
                    raise ValueError("WECOM_MEDIA_STALLED")
                index = next_index
            finally:
                self.lib.FreeMediaData(piece)
        raise ValueError("WECOM_MEDIA_LIMIT")


def normalize_message(message: dict[str, Any], encrypted: dict[str, Any]) -> dict[str, Any]:
    msgid = message.get("msgid")
    sender, recipients = message.get("from"), message.get("tolist", [])
    if (
        not isinstance(msgid, str)
        or not msgid
        or len(msgid) > 200
        or not isinstance(sender, str)
        or not isinstance(recipients, list)
        or not all(isinstance(item, str) for item in recipients)
    ):
        raise ValueError("WECOM_MESSAGE_SCHEMA")
    room = message.get("roomid")
    participants = sorted(set([sender, *recipients]))
    conversation = (
        "wecom-room:" + room
        if room
        else "wecom-chat:"
        + hashlib.sha256(json.dumps(participants, ensure_ascii=False).encode()).hexdigest()
    )
    kind = message.get("msgtype", "unknown")
    body = message.get("text", {}).get("content") if kind == "text" else None
    sent = message.get("msgtime")
    if type(sent) is not int or sent < 0:
        raise ValueError("WECOM_MESSAGE_TIME")
    return {
        "source_record_id": msgid,
        "native_server_id": msgid,
        "conversation_ref": conversation,
        "conversation_kind": "group" if room else "private",
        "sender_ref": sender,
        "sent_at": sent,
        "message_type": {"voice": "audio", "emotion": "sticker", "revoke": "system"}.get(
            kind, kind
        ),
        "body_text": body,
        "wecom_plaintext": message,
        "wecom_envelope": encrypted,
        "media": [],
    }


def archive_page(
    sdk: Any,
    response: dict[str, Any],
    source: dict[str, Any],
    keys: dict[str, str],
    directory: Path,
    seq: int,
) -> tuple[Path | None, int]:
    entries = response.get("chatdata", [])
    if not isinstance(entries, list) or len(entries) > 1000:
        raise ValueError("WECOM_RESPONSE_SCHEMA")
    if not entries:
        return None, seq
    rows, paths = [], set()
    current = seq
    target, temporary = directory / "pending.zip", directory / "building.zip"
    if target.is_symlink() or temporary.is_symlink():
        raise ValueError("UNSAFE_STATE_DIRECTORY")
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for encrypted in entries:
                next_seq = encrypted.get("seq")
                if type(next_seq) is not int or next_seq <= current:
                    raise ValueError("WECOM_SEQUENCE_INVALID")
                version = str(encrypted.get("publickey_ver"))
                if version not in keys:
                    raise ValueError("WECOM_PRIVATE_KEY_VERSION_MISSING")
                message = sdk.decrypt(encrypted, Path(keys[version]))
                row = normalize_message(message, encrypted)
                if encrypted.get("msgid") and encrypted["msgid"] != message["msgid"]:
                    raise ValueError("WECOM_MESSAGE_ID_MISMATCH")
                kind = message.get("msgtype")
                content = message.get(kind, {})
                file_id = content.get("sdkfileid") if isinstance(content, dict) else None
                if file_id:
                    data = sdk.media(file_id)
                    path = "media/" + hashlib.sha256(data).hexdigest() + ".bin"
                    if path not in paths:
                        archive.writestr(path, data)
                        paths.add(path)
                    row["media"] = [{"path": path}]
                    del data
                rows.append(row)
                current = next_seq
            payload = b"".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
                for row in rows
            )
            manifest = {
                **source["source_metadata"],
                "schema_version": "1.0.0",
                "export_id": f"wecom-{seq}-{current}",
                "exported_at": datetime.now(UTC).isoformat(),
                "payload_files": [
                    {
                        "path": "messages.jsonl",
                        "size_bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
                "media_base_path": "media",
                "consent_scope": "official-wecom-authorized-archive",
                "coverage_notes": (
                    "Only enabled, authorized enterprise archive records; "
                    "personal WeChat history is not covered."
                ),
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            archive.writestr("messages.jsonl", payload)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(target)
    return target, current


def sync_wecom(
    client: CollectorClient, config: dict[str, Any], state: Path, sdk: Any = None
) -> dict[str, int]:
    private_directory(state)
    source = client.status()
    if source["kind"] != "wecom_archive":
        raise ValueError("SOURCE_KIND_MISMATCH")
    pending, receipt = state / "pending.zip", state / "pending.json"
    if pending.is_symlink() or receipt.is_symlink():
        raise ValueError("UNSAFE_STATE_DIRECTORY")
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved["source_id"] != source["id"] or not pending.is_file():
            raise ValueError("PENDING_SOURCE_MISMATCH")
        client.upload(pending, str(saved["cursor"]))
        receipt.unlink()
        pending.unlink()
        source = client.status()
    seq = int(source.get("last_cursor") or 0)
    own_sdk = sdk is None
    if own_sdk:
        sdk = FinanceSDK(Path(config["sdk_library"]), config["corp_id"], config["archive_secret"])
    try:
        response = sdk.pull(seq)
        bundle, cursor = archive_page(sdk, response, source, config["private_keys"], state, seq)
        if bundle:
            # Persist exact retry bytes before sending; never regenerate after a timeout.
            temporary_receipt = state / "receipt.tmp"
            fd = os.open(temporary_receipt, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump({"source_id": source["id"], "cursor": cursor}, output)
                output.flush()
                os.fsync(output.fileno())
            temporary_receipt.replace(receipt)
            client.upload(bundle, str(cursor))
            receipt.unlink()
            bundle.unlink()
        client.heartbeat()
        return {"archived_messages": len(response.get("chatdata", [])), "cursor": cursor}
    finally:
        if own_sdk:
            sdk.close()
