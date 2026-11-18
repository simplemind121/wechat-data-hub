"""Create an isolated synthetic test workspace, then run API plus a separate durable worker."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from wdh_api.config import get_settings

root = Path(__file__).resolve().parents[1]
os.chdir(root)
directory = root / ".local" / f"browser-{uuid4().hex}"
directory.mkdir(parents=True, mode=0o700)
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{directory}/test.db"
os.environ["DATA_ROOT"] = str(directory / "archive")
if (root / ".local/models/tesseract").is_dir():
    os.environ.setdefault("OCR_DATA_DIR", str(root / ".local/models/tesseract"))
if (root / ".local/models/asr").is_dir():
    os.environ.setdefault("ASR_MODEL_DIR", str(root / ".local/models/asr"))

if (root / ".local/models/runtime/llama-server").is_file():
    os.environ.setdefault("LOCAL_MODEL_SERVER", str(root / ".local/models/runtime/llama-server"))
if (root / ".local/models/embedding").is_dir():
    os.environ.setdefault(
        "EMBEDDING_MODEL_FILE", str(root / ".local/models/embedding/bge-small-zh-v1.5-q8_0.gguf")
    )
marker = root / ".local/llm-memory.json"
model = (
    Path(json.loads(marker.read_text())["path"])
    if marker.is_file()
    else root / ".local/models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
if model.is_file():
    os.environ.setdefault("LLM_MODEL_FILE", str(model))
get_settings.cache_clear()
command.upgrade(Config("alembic.ini"), "head")
process = subprocess.Popen([sys.executable, "-m", "wdh_api.worker"], cwd=root)
try:
    uvicorn.run(
        "wdh_api.main:create_app", factory=True, host="127.0.0.1", port=18000, access_log=False
    )
finally:
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=15)
