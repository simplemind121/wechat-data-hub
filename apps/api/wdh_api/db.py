from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from wdh_api.config import Settings


def make_engine(settings: Settings) -> Engine:
    args = (
        {"connect_timeout": 3}
        if settings.database_url.startswith("postgresql")
        else {"check_same_thread": False, "timeout": 30}
    )
    engine = create_engine(
        settings.database_url, connect_args=args, pool_pre_ping=True, hide_parameters=True
    )
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def pragmas(connection: object, _: object) -> None:
            connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]
            connection.execute("PRAGMA journal_mode=WAL")  # type: ignore[attr-defined]

    return engine


def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
