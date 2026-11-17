"""A compact, deterministic synthetic demo generated without any real chat data."""

import hashlib
import io
import json
import zipfile


def demo_zip(device: str = "ios") -> bytes:
    rows = [
        {
            "source_record_id": "synthetic-1",
            "native_server_id": "synthetic-server-1",
            "conversation_ref": "合成·产品讨论",
            "sender_ref": "synthetic-lin",
            "sender_name": "合成联系人·林",
            "sent_at": "2026-11-17T11:30:00Z",
            "message_type": "text",
            "body_text": "合成示例：M620 Ultra，50套起订，3200元/套。仅演示，非真实报价。",
        },
        {
            "source_record_id": "synthetic-2",
            "conversation_ref": "合成·产品讨论",
            "sender_ref": "synthetic-self",
            "sender_name": "我（合成）",
            "sent_at": "2026-11-17T11:31:00Z",
            "message_type": "text",
            "body_text": "收到",
            "direction": "outgoing",
        },
        {
            "source_record_id": "synthetic-3",
            "conversation_ref": "合成·产品讨论",
            "sender_ref": "synthetic-self",
            "sender_name": "我（合成）",
            "sent_at": "2026-11-17T11:31:00Z",
            "message_type": "text",
            "body_text": "收到",
            "direction": "outgoing",
        },
        {
            "source_record_id": "synthetic-4",
            "conversation_ref": "合成·日常交流",
            "sender_ref": "synthetic-zhou",
            "sender_name": "合成联系人·周",
            "sent_at": "2026-11-16T08:00:00+08:00",
            "message_type": "text",
            "body_text": "中文、emoji 🧪 和原始换行\n都会保留下来。",
        },
        {
            "source_record_id": "synthetic-5",
            "conversation_ref": "合成·产品讨论",
            "sender_ref": "synthetic-lin",
            "sent_at": "2026-11-17T11:32:00Z",
            "message_type": "file",
            "body_text": "附件缺失示例",
            "media": [{"path": "media/not-exported.pdf"}],
        },
    ]
    payload = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows)
    manifest = {
        "schema_version": "1.0.0",
        "export_id": f"synthetic-demo-{device}",
        "account_ref": "synthetic-demo",
        "device_ref": f"synthetic-demo-{device}",
        "platform": device,
        "os_version": "synthetic",
        "wechat_version": "NOT_TESTED",
        "exporter_name": "wdh-synthetic-factory",
        "exporter_version": "1.0.0",
        "exported_at": "2026-11-17T12:00:00Z",
        "original_timezone": "Asia/Shanghai",
        "data_format": "jsonl-v1",
        "payload_files": [
            {
                "path": "messages.jsonl",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
        "media_base_path": "media",
        "consent_scope": "synthetic-data-only",
        "coverage_notes": "仅合成示例，不代表真实微信客户端兼容性。",
    }
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in {
            "manifest.json": json.dumps(manifest, ensure_ascii=False).encode(),
            "messages.jsonl": payload,
        }.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 17, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return result.getvalue()
