"""Create an isolated synthetic test workspace, then run API plus a separate durable worker."""

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
