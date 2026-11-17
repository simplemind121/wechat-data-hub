"""Compact runtime: migrate, then supervise API and an independent durable worker process."""

import multiprocessing
import threading

import uvicorn
from alembic import command
from alembic.config import Config

from wdh_api.config import get_settings


def worker_main() -> None:
    from wdh_api.worker import main as run_worker

    run_worker()


def main() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    worker = multiprocessing.get_context("spawn").Process(target=worker_main)
    worker.start()
    settings = get_settings()
    server = uvicorn.Server(
        uvicorn.Config(
            "wdh_api.main:create_app",
            factory=True,
            host=settings.app_bind_host,
            port=8000,
            access_log=False,
        )
    )
    stopped = threading.Event()

    def supervise() -> None:
        while not stopped.wait(1):
            if not worker.is_alive():
                server.should_exit = True
                return

    monitor = threading.Thread(target=supervise, daemon=True)
    monitor.start()
    try:
        server.run()
    finally:
        stopped.set()
        if worker.is_alive():
            worker.terminate()
        worker.join(timeout=20)
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=5)


if __name__ == "__main__":
    main()
