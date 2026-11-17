import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def tree_hash(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_factory_is_reproducible_and_declares_boundaries(tmp_path: Path) -> None:
    for name in ("a", "b"):
        subprocess.run(
            [sys.executable, "scripts/generate_fixtures.py", "--output", str(tmp_path / name)],
            cwd=ROOT,
            check=True,
        )
    assert tree_hash(tmp_path / "a") == tree_hash(tmp_path / "b")
    cases = json.loads((tmp_path / "a/cases.json").read_text())
    assert len(cases) >= 25
    assert {
        "duplicate_text",
        "timezone_dst",
        "missing_media",
        "path_traversal",
        "same_name_different_content",
        "invalid_jsonl",
        "cross_workspace",
        "unapproved_entity",
        "zip_bomb",
    } <= {c["id"] for c in cases}
    for manifest_path in (tmp_path / "a").glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text())
        assert manifest["consent_scope"] == "synthetic-data-only"
        for payload in manifest["payload_files"]:
            data = (manifest_path.parent / payload["path"]).read_bytes()
            assert len(data) == payload["size_bytes"]
            assert hashlib.sha256(data).hexdigest() == payload["sha256"]


def test_factory_never_overwrites_an_existing_export(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "private.txt").write_text("keep")
    result = subprocess.run(
        [sys.executable, "scripts/generate_fixtures.py", "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode != 0
    assert (output / "private.txt").read_text() == "keep"
