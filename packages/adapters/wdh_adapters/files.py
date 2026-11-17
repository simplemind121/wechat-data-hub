import csv
import hashlib
import io
import json
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, BinaryIO, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import ijson  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, field_validator, model_validator

ADAPTER_VERSION = "1.0.0"
NORMALIZATION_VERSION = "1.0.0"
MAX_RECORD_BYTES = 2 * 1024 * 1024


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 1000
        or value == "."
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or ":" in value
        or "\x00" in value
    ):
        raise ValueError("UNSAFE_PATH")
    return str(path)


class PayloadFile(BaseModel):
    path: str = Field(max_length=1000)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def path_safe(cls, value: str) -> str:
        return safe_path(value)


class Manifest(BaseModel):
    schema_version: Literal["1.0.0"]
    export_id: str = Field(min_length=1, max_length=200)
    account_ref: str = Field(min_length=1, max_length=200)
    device_ref: str = Field(min_length=1, max_length=200)
    platform: Literal["ios", "macos", "windows", "other"]
    os_version: str = Field(max_length=100)
    wechat_version: str = Field(max_length=100)
    exporter_name: str = Field(max_length=100)
    exporter_version: str = Field(max_length=100)
    exported_at: datetime
    original_timezone: str
    data_format: Literal["jsonl-v1", "json-v1", "csv-v1"]
    payload_files: list[PayloadFile] = Field(min_length=1, max_length=1000)
    media_base_path: str = "media"
    consent_scope: str = Field(min_length=1, max_length=300)
    coverage_notes: str = Field(max_length=4000)
    json_root: Literal["array", "messages"] = "array"
    field_mapping: dict[str, str] = Field(default_factory=dict)
    delimiter: Literal[",", ";", "\t"] = ","

    @model_validator(mode="after")
    def validate_contract(self) -> "Manifest":
        try:
            ZoneInfo(self.original_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("INVALID_TIMEZONE") from exc
        safe_path(self.media_base_path)
        if self.exported_at.tzinfo is None:
            raise ValueError("EXPORTED_AT_REQUIRES_TIMEZONE")
        if len({p.path for p in self.payload_files}) != len(self.payload_files):
            raise ValueError("DUPLICATE_PAYLOAD_PATH")
        if self.data_format == "csv-v1" and not self.field_mapping:
            raise ValueError("CSV_REQUIRES_FIELD_MAPPING")
        return self

    @property
    def certified_namespace(self) -> str | None:
        # Certification is deliberately limited to the documented synthetic fixture contract.
        if (
            self.consent_scope == "synthetic-data-only"
            and self.exporter_version == "1.0.0"
            and self.exporter_name in {"synthetic-fixture-generator", "wdh-synthetic-factory"}
        ):
            return "synthetic-v1"
        return None


@dataclass(frozen=True)
class Record:
    locator: str
    raw: bytes
    payload: dict[str, Any] | None
    error: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


def _record(value: Any, locator: str, raw: bytes | None = None) -> Record:
    encoded = (
        raw if raw is not None else json.dumps(value, ensure_ascii=False, default=str).encode()
    )
    if len(encoded) > MAX_RECORD_BYTES:
        return Record(locator, encoded, None, "RECORD_SIZE_LIMIT")
    if not isinstance(value, dict):
        return Record(locator, encoded, None, "RECORD_NOT_OBJECT")
    return Record(locator, encoded, value)


def iter_records(stream: BinaryIO, manifest: Manifest) -> Iterator[Record]:
    if manifest.data_format == "jsonl-v1":
        number = 0
        while raw := stream.readline(MAX_RECORD_BYTES + 1):
            number += 1
            locator = f"line:{number}"
            if len(raw) > MAX_RECORD_BYTES:
                # Drain this single oversized line without retaining it in memory.
                while not raw.endswith(b"\n"):
                    raw = stream.readline(MAX_RECORD_BYTES + 1)
                    if not raw:
                        break
                yield Record(locator, b"", None, "RECORD_SIZE_LIMIT")
                continue
            if not raw.strip():
                continue
            try:
                value = json.loads(raw.decode("utf-8-sig"), parse_constant=invalid_constant)
                yield _record(value, locator, raw)
            except (ValueError, UnicodeError):
                yield Record(locator, raw, None, "INVALID_JSON")
    elif manifest.data_format == "json-v1":
        prefix = "item" if manifest.json_root == "array" else "messages.item"
        # Validate the root separately; ijson otherwise silently yields nothing for a wrong root.
        start = stream.read(4096).lstrip(b"\xef\xbb\xbf \r\n\t")
        stream.seek(0)
        expected = b"[" if manifest.json_root == "array" else b"{"
        if not start.startswith(expected):
            raise ValueError("JSON_ROOT_MISMATCH")
        if manifest.json_root == "messages":
            found = False
            for prefix_value, event, _ in ijson.parse(stream):
                if prefix_value == "messages":
                    found = event == "start_array"
                    break
            if not found:
                raise ValueError("JSON_ROOT_MISMATCH")
            stream.seek(0)
        try:
            for number, value in enumerate(ijson.items(stream, prefix, use_float=True), 1):
                yield _record(value, f"item:{number}")
        except (ijson.JSONError, UnicodeError) as exc:
            raise ValueError("INVALID_JSON_DOCUMENT") from exc
    else:
        text = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        csv.field_size_limit(MAX_RECORD_BYTES)
        try:
            reader = csv.DictReader(text, delimiter=manifest.delimiter)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("INVALID_CSV_HEADER")
            if not set(manifest.field_mapping.values()) <= set(reader.fieldnames):
                raise ValueError("CSV_MAPPED_COLUMN_MISSING")
            for number, value in enumerate(reader, 1):
                if None in value:
                    yield Record(f"row:{number}", b"", None, "CSV_COLUMN_COUNT")
                else:
                    yield _record(value, f"row:{number}")
        except (csv.Error, UnicodeError) as exc:
            raise ValueError("INVALID_CSV") from exc
        finally:
            text.detach()


def parse_time(value: Any, zone: str) -> tuple[datetime | None, str]:
    if value is None or value == "":
        return None, "unknown"
    precision = "second"
    if isinstance(value, (int, float)) or (
        isinstance(value, str) and re.fullmatch(r"-?\d{9,16}", value)
    ):
        numeric = float(value)
        if abs(numeric) >= 100_000_000_000_000:
            numeric /= 1_000_000
            precision = "microsecond"
        elif abs(numeric) >= 100_000_000_000:
            numeric /= 1000
            precision = "millisecond"
        return datetime.fromtimestamp(numeric, UTC), precision
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        precision = "day"
    elif "." in str(value):
        precision = "millisecond"
    elif len(str(value)) == 16:
        precision = "minute"
    if parsed.tzinfo is None:
        timezone = ZoneInfo(zone)
        possible: set[datetime] = set()
        for fold in (0, 1):
            candidate = parsed.replace(tzinfo=timezone, fold=fold).astimezone(UTC)
            if candidate.astimezone(timezone).replace(tzinfo=None) == parsed:
                possible.add(candidate)
        if len(possible) != 1:
            raise ValueError("AMBIGUOUS_OR_NONEXISTENT_TIME")
        return possible.pop(), precision
    return parsed.astimezone(UTC), precision


def normalize(raw: dict[str, Any], manifest: Manifest) -> dict[str, Any]:
    value = (
        {key: raw.get(column) for key, column in manifest.field_mapping.items()}
        if manifest.field_mapping
        else dict(raw)
    )
    if value.get("account_ref", manifest.account_ref) != manifest.account_ref:
        raise ValueError("ACCOUNT_MISMATCH")
    conversation = value.get("conversation_ref")
    if not isinstance(conversation, str) or not conversation or len(conversation) > 200:
        raise ValueError("CONVERSATION_REQUIRED")
    sent, precision = parse_time(value.get("sent_at"), manifest.original_timezone)
    body = value.get("body_text")
    if body is not None and not isinstance(body, str):
        raise ValueError("BODY_MUST_BE_TEXT")
    original_type = str(value.get("message_type", "unknown"))
    supported = {
        "text",
        "image",
        "video",
        "audio",
        "file",
        "sticker",
        "system",
        "quote",
        "location",
    }
    media = value.get("media") or []
    if not isinstance(media, list) or len(media) > 100:
        raise ValueError("INVALID_MEDIA_REFERENCES")
    for item in media:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("INVALID_MEDIA_REFERENCES")
        safe_path(item["path"])
    return {
        **value,
        "conversation_ref": conversation,
        "sent_at": sent,
        "original_time_text": str(value["sent_at"]) if value.get("sent_at") is not None else None,
        "original_time_precision": precision,
        "body_text": body,
        "search_text": unicodedata.normalize("NFKC", body or "").casefold(),
        "message_type": original_type if original_type in supported else "unknown",
        "original_type_code": original_type,
        "media": media,
        "field_provenance": {key: manifest.field_mapping.get(key, key) for key in value},
        "conversation_kind": value.get("conversation_kind")
        if value.get("conversation_kind") in {"private", "group", "official"}
        else "unknown",
    }


def invalid_constant(_: str) -> None:
    raise ValueError("INVALID_JSON_NUMBER")
