from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a VA Claim Builder RC distribution")
    parser.add_argument("platform", choices=("windows", "macos", "linux", "portable"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    version = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    if args.clean:
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir(exist_ok=True)
    if not args.skip_tests:
        subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, check=True)
    if shutil.which("pyinstaller") is None:
        raise SystemExit("PyInstaller is required. Install requirements-packaging.txt.")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(ROOT / "packaging" / "VAClaimBuilder.spec")], cwd=ROOT, check=True)
    artifacts = [item for item in DIST.iterdir() if item.is_file()]
    if args.platform == "portable":
        archive = shutil.make_archive(str(DIST / f"VAClaimBuilder-{version['display_version'].replace(' ', '-')}-portable"), "zip", DIST)
        artifacts.append(Path(archive))
    manifest = {"application": "VA Claim Builder", "version": version["version"], "display_version": version["display_version"], "target": args.platform, "built_at": datetime.now(timezone.utc).isoformat(), "host_platform": sys.platform, "artifacts": [{"name": p.name, "sha256": checksum(p), "size": p.stat().st_size} for p in artifacts]}
    (DIST / "release-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (DIST / "SHA256SUMS.txt").write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in manifest["artifacts"]), encoding="utf-8")
    print(f"Release output: {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
