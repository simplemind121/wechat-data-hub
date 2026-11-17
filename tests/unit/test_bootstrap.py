import os
import subprocess
import sys
from pathlib import Path


def test_bootstrap_protects_secrets_and_does_not_overwrite() -> None:
    # Run a separate temporary working directory so no developer configuration is touched.
    import tempfile

    script = Path("scripts/bootstrap.py").resolve()
    template = Path(".env.example").read_text()
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / ".env.example").write_text(template)
        result = subprocess.run(
            [sys.executable, str(script)], cwd=folder, capture_output=True, text=True, check=True
        )
        content = (folder / ".env").read_text()
        assert "REPLACE_WITH" not in content
        assert os.stat(folder / ".env").st_mode & 0o777 == 0o600
        assert content not in result.stdout
        subprocess.run([sys.executable, str(script)], cwd=folder, check=True)
        assert (folder / ".env").read_text() == content
