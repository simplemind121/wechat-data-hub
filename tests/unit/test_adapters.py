import io
import json

import pytest
from wdh_adapters.files import Manifest, iter_records, normalize, safe_path


def manifest(format: str = "jsonl-v1", **changes: object) -> Manifest:
    return Manifest.model_validate(
        {
            "schema_version": "1.0.0",
            "export_id": "synthetic",
            "account_ref": "a",
            "device_ref": "d",
            "platform": "ios",
            "os_version": "synthetic",
            "wechat_version": "unknown",
            "exporter_name": "wdh-synthetic-factory",
            "exporter_version": "1.0.0",
            "exported_at": "2026-11-17T12:00:00Z",
            "original_timezone": "Asia/Shanghai",
            "data_format": format,
            "payload_files": [{"path": "messages.jsonl", "size_bytes": 1, "sha256": "a" * 64}],
            "media_base_path": "media",
            "consent_scope": "synthetic-data-only",
            "coverage_notes": "synthetic",
            **changes,
        }
    )


def test_jsonl_bad_line_does_not_drop_following_records() -> None:
    rows = list(iter_records(io.BytesIO(b'{bad\n{"body_text":"ok"}\n'), manifest()))
    assert rows[0].error == "INVALID_JSON"
    assert rows[1].payload == {"body_text": "ok"}
    assert rows[1].locator == "line:2"


def test_json_array_and_explicit_object_root() -> None:
    source = json.dumps({"messages": [{"body_text": "中文🧪"}]}).encode()
    result = list(iter_records(io.BytesIO(source), manifest("json-v1", json_root="messages")))
    assert result[0].payload == {"body_text": "中文🧪"}
    assert len(list(iter_records(io.BytesIO(b"[{},{}]"), manifest("json-v1")))) == 2


def test_csv_requires_explicit_mapping_and_keeps_empty_fields() -> None:
    with pytest.raises(ValueError):
        manifest("csv-v1")
    data = 'id,content,time\n1,"中文,🧪",\n'.encode()
    m = manifest(
        "csv-v1",
        field_mapping={"source_record_id": "id", "body_text": "content", "sent_at": "time"},
    )
    row = list(iter_records(io.BytesIO(data), m))[0]
    assert row.payload == {"id": "1", "content": "中文,🧪", "time": ""}


@pytest.mark.parametrize("path", ["../a", "/a", "C:/a", "a\\b", "a/../b", "", "."])
def test_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError):
        safe_path(path)


@pytest.mark.parametrize(
    "time",
    [
        "2026-11-17T19:30:00+08:00",
        "2026-11-17T11:30:00Z",
        1794915000,
        1794915000000,
        1794915000000000,
    ],
)
def test_time_instant_and_unicode_roundtrip(time: object) -> None:
    value = normalize(
        {
            "source_record_id": "1",
            "conversation_ref": "c",
            "sender_ref": "s",
            "sent_at": time,
            "body_text": "中文🧪 Ｍ６２０\ne\u0301",
        },
        manifest(),
    )
    assert value["sent_at"].isoformat() == "2026-11-17T11:30:00+00:00"
    assert value["body_text"] == "中文🧪 Ｍ６２０\ne\u0301"
    assert value["search_text"] == "中文🧪 m620\né"


def test_missing_time_not_invented_unknown_type_kept() -> None:
    value = normalize({"conversation_ref": "c", "message_type": "vendor-999"}, manifest())
    assert value["sent_at"] is None
    assert value["message_type"] == "unknown"
    assert value["original_type_code"] == "vendor-999"


def test_ambiguous_or_nonexistent_local_time_rejected() -> None:
    for value in ["2026-11-01T01:30:00", "2026-03-08T02:30:00"]:
        with pytest.raises(ValueError, match="AMBIGUOUS_OR_NONEXISTENT_TIME"):
            normalize(
                {"conversation_ref": "c", "sent_at": value},
                manifest(original_timezone="America/New_York"),
            )


def test_generic_server_id_is_never_certified_by_user_manifest() -> None:
    assert not manifest(exporter_name="unknown-exporter").certified_namespace
    assert manifest().certified_namespace == "synthetic-v1"
