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
report = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": "urn:uuid:" + str(uuid4()),
    "version": 1,
    "metadata": {
        "timestamp": datetime.now(UTC).isoformat(),
        "component": {"type": "application", "name": "WeChat Data Hub", "version": "0.2.0"},
        "properties": [
            {
                "name": "wdh:scope",
                "value": "Python installed environment + npm lock; excludes OS/image packages",
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
(root / "THIRD_PARTY_NOTICES.md").write_text("\n".join(notices))
print(f"Generated inventory: {len(components)} components; web runtime license notices included.")
