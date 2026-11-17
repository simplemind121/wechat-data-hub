"""Deterministic, synthetic-only adversarial corpus. Never run against an existing directory."""

import argparse
import base64
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

FIXED_TIME = "2026-11-17T12:00:00Z"


def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def record(key: str, **fields: Any) -> dict[str, Any]:
    return {
        "source_record_id": key,
        "native_server_id": None,
        "account_ref": "synthetic-a",
        "conversation_ref": "synthetic-business",
        "sender_ref": "synthetic-contact-a",
        "sent_at": "2026-11-17T19:30:00+08:00",
        "message_type": "text",
        "body_text": "合成测试消息 🧪",
        "media": [],
        "reply_to": None,
        **fields,
    }


def zip_bytes(items: dict[str, bytes], symlink: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in items.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o120777 if symlink else 0o100600) << 16
            archive.writestr(info, payload)
    return buffer.getvalue()


def generate(output: Path) -> None:
    # A missing final path is required: avoid overwriting any original export, even accidentally.
    output.mkdir(parents=True, exist_ok=False)
    cases: list[dict[str, str]] = []

    def case(key: str, expected: str) -> None:
        cases.append({"id": key, "expected": expected, "classification": "synthetic-only"})

    rows = [
        record("strong-a", native_server_id="synthetic-server-1"),
        record("repeat-a", body_text="收到"),
        record("repeat-b", body_text="收到"),
    ]
    variants: list[tuple[str, str, dict[str, Any]]] = [
        (
            "group_rename",
            "preserve alias history",
            {"conversation_ref": "synthetic-group", "sender_name": "成员改名"},
        ),
        (
            "same_nickname",
            "do not merge identities by nickname",
            {"sender_ref": "synthetic-b", "sender_name": "成员改名"},
        ),
        ("empty_identity", "unresolved sender", {"sender_ref": None}),
        ("timezone_utc", "same instant as +08:00", {"sent_at": "2026-11-17T11:30:00Z"}),
        ("timezone_dst", "require explicit DST offset", {"sent_at": "2026-11-01T01:30:00-04:00"}),
        ("epoch_seconds", "parse seconds explicitly", {"sent_at": 1794915000}),
        ("epoch_millis", "parse milliseconds explicitly", {"sent_at": 1794915000000}),
        ("missing_time", "unresolved; never invent timestamp", {"sent_at": None}),
        (
            "unicode",
            "raw bytes preserved; NFKC search only",
            {"body_text": "中文👨‍👩‍👧 e\u0301 Ｍ６２０\n报价"},
        ),
        (
            "xml_cdata",
            "text only; never resolve entities",
            {"body_text": "<![CDATA[<报价>￥1</报价>]]>"},
        ),
        ("xss", "render as text", {"body_text": '<script>alert("synthetic")</script>'}),
        ("long_text", "bounded streaming", {"body_text": "长文本🧪" * 20000}),
        ("revoke", "preserve event and source", {"message_type": "system", "event": "revoke"}),
        (
            "edit",
            "keep old and new observations",
            {"native_server_id": "synthetic-server-1", "body_text": "合成编辑后的消息"},
        ),
        ("reply_found", "link when target available", {"reply_to": "strong-a"}),
        ("reply_missing", "unresolved reference", {"reply_to": "not-exported"}),
        ("missing_media", "availability=missing", {"media": [{"path": "media/absent.png"}]}),
        ("present_media", "hash and preserve", {"media": [{"path": "media/pixel.png"}]}),
        ("same_content_paths", "one physical blob", {"media": [{"path": "media/copy.png"}]}),
        (
            "same_name_different_content",
            "distinct hashes",
            {"media": [{"path": "other/pixel.png"}]},
        ),
        ("unknown_type", "preserve raw type", {"message_type": "vendor-999"}),
        (
            "csv_formula",
            "escape only on CSV export",
            {"body_text": '=HYPERLINK("https://invalid.example")'},
        ),
    ]
    case("strong_cross_device", "merge only with certified synthetic namespace")
    case("duplicate_text", "two records remain two canonical messages")
    for key, expected, changes in variants:
        rows.append(record(key, **changes))
        case(key, expected)
    for device in ("ios", "macos"):
        folder = output / device
        folder.mkdir()
        device_rows = (
            rows
            if device == "ios"
            else [
                record(
                    "strong-mac",
                    native_server_id="synthetic-server-1",
                    sent_at="2026-11-17T11:30:00Z",
                ),
                record("family", conversation_ref="synthetic-group", body_text="合成私人会话"),
            ]
        )
        payload = b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode() for r in device_rows)
        (folder / "messages.jsonl").write_bytes(payload)
        manifest = {
            "schema_version": "1.0.0",
            "export_id": f"synthetic-{device}-001",
            "account_ref": "synthetic-a",
            "device_ref": f"synthetic-{device}",
            "platform": device,
            "os_version": "synthetic",
            "wechat_version": "NOT_TESTED",
            "exporter_name": "wdh-synthetic-factory",
            "exporter_version": "1.0.0",
            "exported_at": FIXED_TIME,
            "original_timezone": "Asia/Shanghai",
            "data_format": "jsonl-v1",
            "media_base_path": "media",
            "consent_scope": "synthetic-data-only",
            "coverage_notes": "NOT real WeChat data",
            "payload_files": [
                {
                    "path": "messages.jsonl",
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ],
        }
        (folder / "manifest.json").write_bytes(encode(manifest))
    pixel = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jOwoAAAAASUVORK5CYII="
    )
    for name, content in {
        "media/pixel.png": pixel,
        "media/copy.png": pixel,
        "other/pixel.png": b"not-an-image",
    }.items():
        path = output / "ios" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
    adverse = output / "adversarial"
    adverse.mkdir()
    (adverse / "invalid.jsonl").write_bytes(b"{broken\n" + encode(record("valid-after-error")))
    (adverse / "messages.json").write_bytes(encode(rows[:3]))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["id", "content", "time"])
    writer.writeheader()
    writer.writerow({"id": "synthetic-csv", "content": "合成 CSV, 🧪", "time": ""})
    (adverse / "partial.csv").write_text(buffer.getvalue(), encoding="utf-8")
    (adverse / "degraded.html").write_text("<p>合成 HTML 归档</p>", encoding="utf-8")
    (adverse / "degraded.txt").write_text("合成 TXT 归档\n", encoding="utf-8")
    (adverse / "traversal.zip").write_bytes(zip_bytes({"../outside.txt": b"synthetic"}))
    (adverse / "absolute.zip").write_bytes(zip_bytes({"/tmp/outside.txt": b"synthetic"}))
    (adverse / "symlink.zip").write_bytes(zip_bytes({"link": b"../../outside"}, symlink=True))
    (adverse / "ratio.zip").write_bytes(zip_bytes({"large.txt": b"0" * 1_048_576}))
    (adverse / "unapproved_entity.json").write_bytes(
        encode(
            {
                "entity_type": "quotation",
                "status": "pending_review",
                "supplier_name": "合成同名供应商",
                "candidates": [{"currency": "CNY", "moq": 50}, {"currency": "USD", "moq": 100}],
                "evidence_source_record_ids": ["strong-a"],
                "privacy_scope": "private",
            }
        )
    )
    for key, expected in {
        "invalid_jsonl": "quarantine invalid row; continue valid rows",
        "partial_csv": "explicit field mapping",
        "degraded_html_txt": "archive with completeness=partial",
        "path_traversal": "reject",
        "absolute_path": "reject",
        "symlink": "reject",
        "zip_bomb": "reject high ratio",
        "cross_workspace": "deny foreign workspace objects",
        "unapproved_entity": "deny outbox",
        "supplier_conflict": "manual review required",
        "odoo_timeout": "read back before retry",
    }.items():
        case(key, expected)
    (output / "cases.json").write_bytes(encode(cases))
    (output / "README.md").write_text(
        "# Synthetic corpus v1\nAll identities and records are synthetic.\n"
        "cases.json declares later-stage expectations; "
        "generation does not test those features.\n"
        "Archive fixtures are small inert attacks. Do not extract using an untrusted unzip path.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)
