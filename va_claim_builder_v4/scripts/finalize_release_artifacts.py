
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def finalize(directory: Path) -> None:
    manifest_path = directory / "release-manifest.json"
    sums_path = directory / "SHA256SUMS.txt"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.name not in {manifest_path.name, sums_path.name}
    )
    manifest["artifacts"] = [
        {"name": path.name, "size": path.stat().st_size, "sha256": digest(path)}
        for path in files
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    sums_path.write_text(
        "".join(f"{item['sha256']}  {item['name']}\n" for item in manifest["artifacts"]),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    finalize(parser.parse_args().directory.resolve())
