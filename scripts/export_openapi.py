import argparse
import json
from pathlib import Path

from wdh_api.config import Settings
from wdh_api.main import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    path = Path("contracts/implemented-openapi.json")
    expected = json.dumps(create_app(Settings(_env_file=None)).openapi(), indent=2) + "\n"
    if arguments.check:
        if path.read_text() != expected:
            raise SystemExit("Implemented API contract drift; run make contract")
    else:
        path.write_text(expected)
