"""Explicit local model installation from a pinned public catalog; never accepts arbitrary URLs."""

import argparse
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import time
import urllib.request
from collections.abc import Callable
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from wdh_storage.cas import ContentStore

from wdh_api.config import Settings, get_settings


def catalog() -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads(files("wdh_api").joinpath("model_assets.json").read_text())
    )


def revision(kind: str) -> str:
    return hashlib.sha256(json.dumps(catalog()[kind], sort_keys=True).encode()).hexdigest()


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        if urlsplit(newurl).scheme != "https":
            raise ValueError("MODEL_REQUIRES_HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextmanager
def download(url: str) -> Any:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname not in {"github.com", "raw.githubusercontent.com", "huggingface.co"}
        or parts.username
        or parts.password
    ):
        raise ValueError("UNTRUSTED_MODEL_SOURCE")
    opener = urllib.request.build_opener(HTTPSRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "WeChat-Data-Hub-model-installer"})
    with opener.open(request, timeout=30) as response:
        yield response


def install(
    kind: str,
    settings: Settings,
    root: Path | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, Any]:
    spec = catalog()[kind]
    directory = (root or settings.data_root / "models") / ("tesseract" if kind == "ocr" else kind)
    ContentStore._directory(directory.absolute())
    missing = []
    for item in spec["files"]:
        target = directory / item["name"]
        if target.is_symlink():
            raise ValueError("UNSAFE_MODEL_PATH")
        if target.exists():
            if sha(target) != item["sha256"]:
                raise ValueError("MODEL_HASH_MISMATCH")
        else:
            missing.append(item)
    required = sum(item["bytes"] for item in missing)
    if not missing:
        return {"kind": kind, "status": "already_installed", "revision": revision(kind)}
    if required + 33_554_432 > shutil.disk_usage(directory).free:
        raise ValueError("MODEL_STORAGE_LIMIT")
    started = time.monotonic()

    def check() -> None:
        if time.monotonic() - started > 600:
            raise ValueError("MODEL_DOWNLOAD_TIMEOUT")
        if checkpoint:
            checkpoint()

    class Reader(io.RawIOBase):
        def __init__(self, source: Any, maximum: int):
            self.source, self.maximum = source, maximum
            self.digest, self.count = hashlib.sha256(), 0

        def read(self, size: int = -1) -> bytes:
            check()
            data: bytes = self.source.read(size)
            self.count += len(data)
            if self.count > self.maximum:
                raise ValueError("MODEL_DOWNLOAD_SIZE_LIMIT")
            self.digest.update(data)
            return data

    with tempfile.TemporaryDirectory(prefix="install-", dir=directory) as temporary:
        staging = Path(temporary)
        if "archive_sha256" in spec:
            with download(spec["url"]) as response:
                reader = Reader(response, spec["archive_bytes"])
                total = 0
                selected = {item["name"] for item in missing if "alias_of" not in item}
                mode: Literal["r|gz", "r|bz2"] = (
                    "r|gz" if spec.get("format") == "tar.gz" else "r|bz2"
                )
                with tarfile.open(fileobj=reader, mode=mode) as archive:
                    for member in archive:
                        total += member.size
                        if total > 1_073_741_824:
                            raise ValueError("MODEL_ARCHIVE_SIZE_LIMIT")
                        name = PurePosixPath(member.name)
                        if name.is_absolute() or ".." in name.parts:
                            raise ValueError("UNSAFE_MODEL_ARCHIVE")
                        if name.name in selected:
                            if not member.isfile() or member.size > 134_217_728:
                                raise ValueError("UNSAFE_MODEL_ARCHIVE")
                            source = archive.extractfile(member)
                            if source is None:
                                raise ValueError("INVALID_MODEL_ARCHIVE")
                            with (staging / name.name).open("xb") as output:
                                while chunk := source.read(1_048_576):
                                    check()
                                    output.write(chunk)
                while reader.read(1_048_576):
                    pass
                if (
                    reader.count != spec["archive_bytes"]
                    or reader.digest.hexdigest() != spec["archive_sha256"]
                ):
                    raise ValueError("MODEL_HASH_MISMATCH")
            for item in missing:
                if "alias_of" in item:
                    origin = staging / item["alias_of"]
                    if not origin.is_file():
                        origin = directory / item["alias_of"]
                    os.link(origin, staging / item["name"])
        else:
            for item in missing:
                with download(item["url"]) as response:
                    reader = Reader(response, item["bytes"])
                    with (staging / item["name"]).open("xb") as output:
                        while chunk := reader.read(1_048_576):
                            output.write(chunk)
                    if reader.count != item["bytes"] or reader.digest.hexdigest() != item["sha256"]:
                        raise ValueError("MODEL_HASH_MISMATCH")
        for item in missing:
            path = staging / item["name"]
            if (
                not path.is_file()
                or path.stat().st_size != item["bytes"]
                or sha(path) != item["sha256"]
            ):
                raise ValueError("MODEL_HASH_MISMATCH")
        check()
        for item in missing:
            source, target = staging / item["name"], directory / item["name"]
            source.chmod(0o500 if item.get("executable") else 0o400)
            try:
                os.link(source, target)
            except FileExistsError:
                if target.is_symlink() or sha(target) != item["sha256"]:
                    raise ValueError("MODEL_HASH_MISMATCH") from None
    return {"kind": kind, "status": "installed", "revision": revision(kind), "bytes": required}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install"])
    parser.add_argument("kind", choices=[key for key in catalog() if key != "schema_version"])
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    print(json.dumps(install(args.kind, get_settings(), args.root), indent=2))


if __name__ == "__main__":
    main()
