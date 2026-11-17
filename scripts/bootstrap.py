"""Generate local configuration without printing or replacing secrets."""

import os
import secrets
from pathlib import Path


def initialize(path: Path = Path(".env")) -> None:
    password = secrets.token_hex(32)
    content = Path(".env.example").read_text()
    content = content.replace("REPLACE_WITH_SECRET", password)
    content = content.replace("REPLACE_WITH_STRONG_SECRET", password)
    content = content.replace("REPLACE_WITH_STRONG_RANDOM_SECRET", secrets.token_hex(48))
    content = content.replace("/var/lib/wechat-hub", str(Path(".local/data").resolve()))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print("Local configuration exists; left unchanged.")
        return
    with os.fdopen(fd, "w") as file:
        file.write(content)
    print("Created .env (0600). No default user or password has been provisioned.")


if __name__ == "__main__":
    initialize()
