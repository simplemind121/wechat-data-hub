import argparse
import getpass
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from wdh_storage.cas import ContentStore

from wdh_api.backup import create_backup, restore_backup
from wdh_api.config import Settings, get_settings
from wdh_api.db import make_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Local backup and fail-closed restore")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--output", type=Path)
    backup.add_argument("--password-file", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("source", type=Path)
    restore.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    if args.password_file:
        if args.password_file.stat().st_mode & 0o077:
            parser.error("Password file must be private (0600)")
        password = args.password_file.read_text().rstrip("\r\n")
    else:
        password = getpass.getpass("Backup passphrase (16+ characters): ")
    if args.command == "backup":
        settings = get_settings()
        engine = make_engine(settings)
        output = args.output or settings.data_root / "exports" / (
            datetime.now(UTC).strftime("backup-%Y%m%d-%H%M%S") + ".wdhbak"
        )
        result = create_backup(engine, ContentStore(settings.data_root), output, password)
        engine.dispose()
    else:
        url, root = os.getenv("RESTORE_DATABASE_URL"), os.getenv("RESTORE_DATA_ROOT")
        if not url or not root:
            parser.error("Set RESTORE_DATABASE_URL and RESTORE_DATA_ROOT to NEW empty destinations")
        result = restore_backup(
            args.source, password, Settings(database_url=url, data_root=Path(root))
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
