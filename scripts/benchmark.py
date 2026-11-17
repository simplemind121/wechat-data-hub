"""Import 100k synthetic records and preserve measured evidence. Never use real data."""

import hashlib
import json
import os
import platform
import resource
import statistics
import time
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from wdh_api.config import Settings, get_settings
from wdh_api.main import create_app
from wdh_api.worker import Worker
from wdh_domain.models import RawRecord

root = Path(__file__).resolve().parents[1]
os.chdir(root)
directory = root / ".local" / f"benchmark-{uuid4().hex}"
directory.mkdir(parents=True, mode=0o700)
count = int(os.getenv("BENCHMARK_ROWS", "100000"))
base = os.getenv("BENCHMARK_POSTGRES_URL")
if base:
    controller = create_engine(base, isolation_level="AUTOCOMMIT")
    name = "wdhbench_" + uuid4().hex
    with controller.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    controller.dispose()
    database_url = make_url(base).set(database=name).render_as_string(hide_password=False)
else:
    database_url = f"sqlite+pysqlite:///{directory}/benchmark.db"
os.environ["DATABASE_URL"] = database_url
get_settings.cache_clear()
command.upgrade(Config("alembic.ini"), "head")
get_settings.cache_clear()
payload = directory / "messages.jsonl"
with payload.open("wb") as stream:
    for number in range(count):
        record = {
            "source_record_id": f"synthetic-{number}",
            "conversation_ref": "synthetic-benchmark",
            "sender_ref": "synthetic-sender",
            "sent_at": 1794915000 + number,
            "message_type": "text",
            "body_text": f"合成压测 M620 报价 benchmark-{number} " + "context " * 60,
        }
        stream.write((json.dumps(record, ensure_ascii=False) + "\n").encode())
with payload.open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
manifest = {
    "schema_version": "1.0.0",
    "export_id": "synthetic-benchmark",
    "account_ref": "synthetic-benchmark",
    "device_ref": "synthetic-benchmark",
    "platform": "other",
    "os_version": "synthetic",
    "wechat_version": "NOT_TESTED",
    "exporter_name": "wdh-benchmark",
    "exporter_version": "1.0.0",
    "exported_at": "2026-11-17T12:00:00Z",
    "original_timezone": "UTC",
    "data_format": "jsonl-v1",
    "consent_scope": "synthetic-data-only",
    "coverage_notes": "100k synthetic source, no real personal data",
    "media_base_path": "media",
    "payload_files": [
        {"path": payload.name, "size_bytes": payload.stat().st_size, "sha256": checksum}
    ],
}
settings = Settings(database_url=database_url, data_root=directory / "archive")
app = create_app(settings)
started = time.perf_counter()
with TestClient(app) as client:
    result = client.post(
        "/api/v1/auth/setup",
        json={"username": "benchmark-owner", "password": "synthetic-benchmark-password"},
    )
    if result.status_code != 201:
        raise RuntimeError("Synthetic benchmark setup failed")
    client.headers["x-csrf-token"] = result.json()["csrf_token"]
    with payload.open("rb") as stream:
        imported = client.post(
            "/api/v1/imports",
            data={"manifest": json.dumps(manifest)},
            files={"file": (payload.name, stream)},
        )
    if imported.status_code != 202:
        raise RuntimeError(f"Synthetic upload failed with status {imported.status_code}")
    worker = Worker(settings, app.state.factory)
    original_chunk = worker.chunk
    processed = 0

    def measured_chunk(*args):
        global processed
        original_chunk(*args)
        processed += len(args[-1])
        if processed % 10000 == 0:
            print(
                json.dumps(
                    {
                        "processed": processed,
                        "elapsed_seconds": round(time.perf_counter() - started, 2),
                    }
                ),
                flush=True,
            )

    worker.chunk = measured_chunk
    worker.run_once()
    status = client.get("/api/v1/jobs/" + imported.json()["job_id"]).json()
    if status["status"] != "completed":
        raise RuntimeError("Synthetic ingest did not complete: " + status["status"])
    duration = time.perf_counter() - started
    timings = []
    for number in range(30):
        before = time.perf_counter()
        response = client.get(
            "/api/v1/search",
            params={"q": ["报价", "M620", "benchmark-99999"][number % 3], "limit": 50},
        )
        if response.status_code != 200:
            raise RuntimeError("Search failed")
        timings.append(time.perf_counter() - before)
    with app.state.factory() as session:
        normalized = session.scalar(
            select(func.count())
            .select_from(RawRecord)
            .where(RawRecord.parse_status == "normalized")
        )
    report = {
        "scope": "synthetic-only",
        "database": app.state.engine.dialect.name,
        "source_records": count,
        "normalized_records": normalized,
        "source_bytes": payload.stat().st_size,
        "ingest_seconds": round(duration, 3),
        "search_samples_seconds": timings,
        "search_p95_seconds": sorted(timings)[28],
        "search_median_seconds": statistics.median(timings),
        "process_max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "hardware": {"platform": platform.platform(), "cpu_count": os.cpu_count()},
        "api_transport": "in-process HTTP TestClient with actual database and serialization",
        "acceptance": {
            "AC-105": count >= 100000 and payload.stat().st_size >= 50_000_000,
            "AC-603": sorted(timings)[28] < 2.0 and app.state.engine.dialect.name == "postgresql",
        },
    }
    destination = root / "docs/evidence/benchmark-100k.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
