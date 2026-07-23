from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
import hashlib
from pathlib import Path


def bundle_executable(app: Path) -> Path:
    if app.is_file():
        return app
    candidates = (
        app / "Contents" / "MacOS" / "VAClaimBuilder",
        app / "VAClaimBuilder.exe",
        app / "VAClaimBuilder",
    )
    for executable in candidates:
        if executable.is_file():
            return executable
    raise FileNotFoundError(f"Packaged executable is missing under: {app}")


def run_mode(executable: Path, home: Path, marker: Path, variable: str, timeout: int) -> dict:
    env = dict(os.environ)
    env["VCB_HOME"] = str(home)
    env["VCB_LOCAL_ONLY"] = "true"
    env[variable] = str(marker)
    started = time.monotonic()
    process = subprocess.run([str(executable)], env=env, timeout=timeout, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Packaged application exited {process.returncode}: {process.stderr[-1000:]}")
    if not marker.is_file():
        raise RuntimeError(f"Packaged application did not create smoke marker: {marker}")
    result = json.loads(marker.read_text(encoding="utf-8"))
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a frozen VA Claim Builder application")
    parser.add_argument("app", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    executable = bundle_executable(args.app.resolve())
    with tempfile.TemporaryDirectory(prefix="vcb-rc2-smoke-") as temporary:
        root = Path(temporary)
        ui = run_mode(executable, root / "UI Application Data", root / "ui.json", "VCB_PACKAGED_UI_SMOKE_MARKER", args.timeout)
        workflow = run_mode(executable, root / "Workflow Application Data", root / "workflow.json", "VCB_PACKAGED_SMOKE_OUTPUT", args.timeout)
        result = {"bundle": str(args.app.resolve()), "ui": ui, "workflow": workflow}
        output = args.output or args.app.parent / "packaged-smoke-result.json"
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        manifest_path = output.parent / "release-manifest.json"
        sums_path = output.parent / "SHA256SUMS.txt"
        if manifest_path.is_file() and sums_path.is_file():
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["packaged_smoke_test"] = {"passed": True, "result_file": output.name}
            manifest["artifacts"] = [item for item in manifest["artifacts"] if item["name"] != output.name]
            manifest["artifacts"].append({"name": output.name, "size": output.stat().st_size, "sha256": digest})
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            sums_path.write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in manifest["artifacts"]), encoding="utf-8")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
