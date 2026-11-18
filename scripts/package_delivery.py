"""Package a committed source snapshot and explicitly locked Docker images without local data."""

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO


class DigestWriter:
    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream
        self.digest = hashlib.sha256()
        self.count = 0

    def write(self, data: bytes) -> int:
        self.digest.update(data)
        self.count += len(data)
        return self.stream.write(data)

    def flush(self) -> None:
        self.stream.flush()


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/workspace"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise SystemExit("Commit the complete reviewed snapshot before packaging.")
    locked = dict(line.split() for line in Path("images.lock").read_text().splitlines() if line)
    for name, expected in locked.items():
        actual = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", name], text=True
        ).strip()
        if actual != expected:
            raise SystemExit("Image does not match images.lock: " + name)
    prefix = f"WeChat_Data_Hub_v{version}/"
    output = args.output.resolve()
    source = output / f"WeChat_Data_Hub_source_v{version}.zip"
    complete = output / f"WeChat_Data_Hub_v{version}.zip"
    manifest_path = output / f"WeChat_Data_Hub_DELIVERY_MANIFEST_v{version}.json"
    if any(path.exists() for path in (source, complete, manifest_path)):
        raise SystemExit("A delivery artifact already exists; refusing to overwrite it.")
    fd, temporary = tempfile.mkstemp(prefix="wdh-source-", suffix=".zip", dir=output)
    os.close(fd)
    try:
        subprocess.run(
            [
                "git",
                "archive",
                "--format=zip",
                "--prefix=" + prefix,
                "--output=" + temporary,
                commit,
            ],
            check=True,
        )
        os.link(temporary, source)
    finally:
        Path(temporary).unlink(missing_ok=True)
    manifest: dict[str, Any] = {
        "application_version": version,
        "git_commit": commit,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "platform": "linux/amd64",
        "images": locked,
        "source_sha256": sha(source),
        "release_scope": "Usable local OCR/ASR/AI increment; not a full-spec production RC",
        "test_scope": "Synthetic fixtures and actual local models; no real WeChat/Odoo instance",
        "model_policy": "OCR weights and engines included; "
        "ASR/BGE/Qwen weights require explicit first download",
        "excluded": [
            ".env",
            ".local",
            ".git",
            "data volumes",
            "accounts",
            "chat records",
            "optional model weights",
        ],
        "real_source_validation": "BLOCKED",
        "real_odoo_validation": "BLOCKED",
    }
    image_name = f"WeChat_Data_Hub_images_v{version}.tar.gz"
    with zipfile.ZipFile(complete, "x", allowZip64=True) as package:
        with zipfile.ZipFile(source) as snapshot:
            for info in snapshot.infolist():
                relative = info.filename.removeprefix(prefix)
                if relative == ".env" or relative.startswith((".local/", ".git/")):
                    raise ValueError("Unexpected private file in source snapshot")
                info.compress_type = zipfile.ZIP_DEFLATED
                package.writestr(info, snapshot.read(info.filename))
        with package.open(prefix + image_name, "w", force_zip64=True) as entry:
            writer = DigestWriter(entry)
            with gzip.GzipFile(fileobj=writer, mode="wb", compresslevel=1, mtime=0) as compressed:
                process = subprocess.Popen(
                    ["docker", "save", *locked], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                if process.stdout is None:
                    raise RuntimeError("Docker export stream unavailable")
                while data := process.stdout.read(1_048_576):
                    compressed.write(data)
                _, error = process.communicate()
                if process.returncode:
                    raise RuntimeError(error.decode("utf-8", "replace")[-2000:])
            manifest["image_archive_sha256"] = writer.digest.hexdigest()
            manifest["image_archive_bytes"] = writer.count
        package.writestr(
            prefix + "DELIVERY_MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
    with zipfile.ZipFile(complete) as package:
        bad = package.testzip()
        if bad:
            raise ValueError("Package CRC verification failed: " + bad)
    manifest["complete_bundle_sha256"] = sha(complete)
    manifest["complete_bundle_bytes"] = complete.stat().st_size
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    for path in (source, complete):
        checksum = path.with_name(path.name + ".sha256")
        with checksum.open("x") as stream:
            stream.write(sha(path) + "  " + path.name + "\n")
    print(
        json.dumps(
            {
                "bundle": str(complete),
                "bytes": complete.stat().st_size,
                "sha256": manifest["complete_bundle_sha256"],
                "source": str(source),
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
