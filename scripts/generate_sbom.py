"""Inventory installed Python distributions and the complete npm lockfile without private data."""

import importlib.metadata as metadata
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
components = []
license_rows = []
for distribution in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"]):
    name = distribution.metadata["Name"]
    version = distribution.version
    license_value = (
        distribution.metadata.get("License-Expression")
        or distribution.metadata.get("License")
        or "NOASSERTION"
    )
    if len(license_value) > 150 or "\n" in license_value:
        license_value = "NOASSERTION (inspect distribution license files)"
    components.append(
        {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
            "properties": [
                {"name": "wdh:license-metadata", "value": license_value},
                {"name": "wdh:inventory-scope", "value": "runtime-and-development"},
            ],
        }
    )
    license_rows.append(("Python", name, version, license_value))
lock = json.loads((root / "apps/web/package-lock.json").read_text())
for path, item in lock["packages"].items():
    if not path:
        continue
    name = path.split("node_modules/")[-1]
    version = item.get("version", "unknown")
    license_value = str(item.get("license", "NOASSERTION"))
    components.append(
        {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:npm/{name.replace('@', '%40')}@{version}",
            "scope": "optional" if item.get("dev") or item.get("optional") else "required",
            "properties": [{"name": "wdh:license-metadata", "value": license_value}],
        }
    )
    license_rows.append(("npm", name, version, license_value))
catalog = json.loads((root / "apps/api/wdh_api/model_assets.json").read_text())
for kind, item in catalog.items():
    if kind == "schema_version":
        continue
    components.append(
        {
            "type": "application" if kind == "runtime" else "machine-learning-model",
            "name": "wdh-local-" + kind,
            "version": item.get(
                "version",
                "catalog-sha256:"
                + __import__("hashlib")
                .sha256(json.dumps(item, sort_keys=True).encode())
                .hexdigest()[:16],
            ),
            "scope": "required" if kind in {"ocr", "runtime"} else "optional",
            "properties": [
                {"name": "wdh:asset-manifest", "value": "apps/api/wdh_api/model_assets.json"},
                {
                    "name": "wdh:license-metadata",
                    "value": item.get("license", item.get("model_license", "NOASSERTION")),
                },
            ],
        }
    )
components.append(
    {
        "type": "library",
        "name": "pgvector",
        "version": "0.8.7",
        "properties": [
            {"name": "wdh:source-commit", "value": "f37c13f68b57d2c3472b2214fbcff699d6d34876"},
            {"name": "wdh:license-metadata", "value": "PostgreSQL"},
        ],
    }
)
report = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": "urn:uuid:" + str(uuid4()),
    "version": 1,
    "metadata": {
        "timestamp": datetime.now(UTC).isoformat(),
        "component": {"type": "application", "name": "WeChat Data Hub", "version": "0.3.0"},
        "properties": [
            {
                "name": "wdh:scope",
                "value": "Python environment + npm lock + native/model catalog; excludes full OS",
            }
        ],
    },
    "components": components,
}
(root / "docs/evidence/sbom.cdx.json").write_text(json.dumps(report, indent=2) + "\n")
rows = [
    "# Dependency license inventory",
    "",
    "Installed distribution metadata + npm lockfile; includes development/optional packages.",
    "NOASSERTION is not approval. This is not a legal opinion or OS/image SBOM.",
    "",
    "| Ecosystem | Package | Version | Declared license |",
    "| --- | --- | --- | --- |",
]
rows.extend("| " + " | ".join(item) + " |" for item in license_rows)
(root / "docs/DEPENDENCIES.md").write_text("\n".join(rows) + "\n")
notices = [
    "# Bundled web runtime notices",
    "",
    "Application source uses its owner’s license. Third-party runtime notices follow.",
    "",
]
for name in ("react", "react-dom", "scheduler", "@tanstack/react-query", "@tanstack/query-core"):
    directory = root / "apps/web/node_modules" / name
    license_file = next(
        (p for p in (directory / "LICENSE", directory / "LICENSE.md") if p.exists()), None
    )
    if license_file:
        notices.extend(["## " + name, "", license_file.read_text(), ""])
notices.extend(
    [
        "## Local processing",
        "",
        "Tesseract and tessdata_fast: Apache-2.0. llama.cpp b12488: MIT; "
        "upstream notices in docs/licenses/llama.cpp-b12488.",
        "pgvector 0.8.7: PostgreSQL license; source in infra/postgres.Dockerfile; "
        "notice in docs/licenses/pgvector.",
        "Optional Whisper weights: MIT. BGE-small-zh-v1.5: MIT. "
        "Qwen2.5-0.5B-Instruct: Apache-2.0. Exact assets/SHA: apps/api/wdh_api/model_assets.json.",
        "sherpa-onnx: Apache-2.0; soundfile: BSD-3-Clause; "
        "bundled dynamic libsndfile: LGPL-2.1-or-later. Wheels retain upstream LICENSE/COPYING; "
        "no static linking or modification of libsndfile.",
        "Runtime images retain Python wheel and Debian/Alpine package license files. "
        "This inventory is not a full OS or legal audit.",
        "",
    ]
)
(root / "THIRD_PARTY_NOTICES.md").write_text("\n".join(notices))
print(f"Generated inventory: {len(components)} components; web runtime license notices included.")
