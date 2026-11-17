"""Explicit local CLI demo seeding; no hard-coded account or password."""

import argparse
import getpass
import io
import os
import time
from pathlib import Path

from sqlalchemy import select, update
from wdh_domain.models import Job, Membership, SetupLock, User, Workspace
from wdh_storage.cas import ContentStore

from wdh_api.config import get_settings
from wdh_api.db import make_engine, sessions
from wdh_api.demo import demo_zip
from wdh_api.ingest import accept_upload
from wdh_api.security import Principal, audit, password_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id")
    args = parser.parse_args()
    settings = get_settings()
    engine = make_engine(settings)
    factory = sessions(engine)
    with factory() as session:
        initialized = session.scalar(select(User.id).limit(1))
    if not initialized:
        print("First run: create a local administrator. No default credentials are used.")
        username = os.getenv("SEED_ADMIN_USERNAME") or input("Administrator username: ")
        password_file = os.getenv("SEED_ADMIN_PASSWORD_FILE")
        if password_file:
            file = Path(password_file)
            if file.stat().st_mode & 0o077:
                raise ValueError("Password file must have mode 0600")
            password = file.read_text().rstrip("\r\n")
        else:
            password = getpass.getpass("Password (12+ characters): ")
        from wdh_api.routes import Setup

        validated = Setup(username=username, password=password)
        with factory.begin() as session:
            claimed = session.execute(
                update(SetupLock)
                .where(SetupLock.id == 1, SetupLock.consumed.is_(False))
                .values(consumed=True)
                .returning(SetupLock.id)
            ).scalar()
            if not claimed:
                raise ValueError("Administrator already initialized")
            workspace = Workspace(name=validated.workspace_name)
            owner = User(
                username=validated.username, password_hash=password_hash(validated.password)
            )
            session.add_all([workspace, owner])
            session.flush()
            session.add(Membership(workspace_id=workspace.id, user_id=owner.id, role="admin"))
            audit(session, Principal(owner.id, workspace.id, "admin", owner.username), "auth.setup")
    with factory() as session:
        query = select(Membership).where(Membership.role == "admin")
        if args.workspace_id:
            query = query.where(Membership.workspace_id == args.workspace_id)
        member = session.scalar(query.order_by(Membership.created_at).limit(1))
        if not member:
            raise ValueError("No matching administrator workspace")
        user = session.get(User, member.user_id)
        if not user:
            raise ValueError("Administrator unavailable")
        who = Principal(user.id, member.workspace_id, member.role, user.username)
        result = accept_upload(
            session,
            ContentStore(settings.data_root),
            who,
            io.BytesIO(demo_zip()),
            None,
            "synthetic-example.zip",
            settings.upload_max_files,
            settings.import_max_bytes,
        )
    for _ in range(120):
        with factory() as session:
            job = session.get(Job, result["job_id"])
            if job and job.status == "completed":
                print("Synthetic example imported. Both repeated messages were preserved.")
                engine.dispose()
                return
            if job and job.status in {"failed_permanent", "dead_letter", "cancelled"}:
                raise RuntimeError("Demo job failed; inspect its status in the local UI")
        time.sleep(0.5)
    raise RuntimeError("Demo is archived and queued; start the worker and check job status")


if __name__ == "__main__":
    main()
