from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "release"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def architecture_report() -> dict[str, str]:
    return {
        "host_machine": platform.machine(),
        "python_machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "macos_version": platform.mac_ver()[0],
    }


def machine_label(machine: str | None = None) -> str:
    value = machine or platform.machine()
    return "x64" if value.lower() in {"amd64", "x86_64"} else value


def release_directory_name(display_version: str, target: str, machine: str | None = None) -> str:
    platform_label = {"macos": "macOS", "windows": "Windows", "linux": "Linux", "portable": "portable"}[target]
    return f"VAClaimBuilder-{display_version.replace(' ', '-')}-{platform_label}-{machine_label(machine)}"


def build_command(spec: Path, dist: Path, work: Path, *, verbose: bool = False) -> list[str]:
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--distpath", str(dist), "--workpath", str(work)]
    if verbose:
        command += ["--log-level", "DEBUG"]
    command.append(str(spec))
    return command


def run_logged(command: list[str], *, cwd: Path, log: Path, timeout: int, env: dict[str, str] | None = None) -> float:
    started = time.monotonic()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"COMMAND: {' '.join(command)}\n")
        handle.flush()
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, text=True)
        try:
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise RuntimeError(f"Build timed out after {timeout} seconds; see {log}")
    if return_code:
        raise RuntimeError(f"Command failed with exit code {return_code}; see {log}")
    return time.monotonic() - started


def dependency_report() -> dict[str, str]:
    names = ("PyInstaller", "PySide6", "shiboken6", "pydantic", "openai", "httpx", "pypdf", "Pillow", "pytesseract", "cryptography", "tenacity", "python-docx")
    report = {}
    for name in names:
        try:
            report[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report[name] = "not installed"
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build a reproducible VA Claim Builder RC distribution")
    result.add_argument("platform", choices=("windows", "macos", "linux", "portable"))
    result.add_argument("--clean", action="store_true")
    result.add_argument("--skip-tests", action="store_true")
    result.add_argument("--verbose", action="store_true")
    result.add_argument("--diagnostic", action="store_true")
    result.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--keep-work", action="store_true")
    result.add_argument("--timeout", type=int, default=900)
    result.add_argument("--adhoc-sign", action="store_true")
    result.add_argument("--release-version", help="Override packaged PEP 440 version, for example 4.2.0rc3")
    result.add_argument("--display-version", help="Override packaged display version, for example '4.2.0 RC3'")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    version = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    if args.release_version or args.display_version:
        if not (args.release_version and args.display_version):
            raise SystemExit("--release-version and --display-version must be provided together")
        version = {**version, "version": args.release_version, "display_version": args.display_version}
    output_root = args.output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for incomplete in output_root.glob(".*.incomplete-*"):
            if incomplete.is_dir():
                shutil.rmtree(incomplete, ignore_errors=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    build_root = ROOT / "build" / f"release-{uuid.uuid4().hex[:8]}"
    staging_dist = build_root / "dist"
    work = build_root / "work"
    failure_log = output_root / "build-logs" / f"macos-build-{stamp}.log"
    machine = machine_label()
    final_name = release_directory_name(version["display_version"], args.platform, machine)
    final = output_root / final_name
    pending = output_root / f".{final_name}.incomplete-{uuid.uuid4().hex[:8]}"
    started = time.monotonic()
    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit("PyInstaller is missing. Create a clean environment and install requirements-packaging.txt.")
    env = dict(os.environ)
    env["VCB_SOURCE_ROOT"] = str(ROOT)
    env["PYINSTALLER_CONFIG_DIR"] = str(build_root / "pyinstaller-config")
    packaged_version_file = build_root / "version.json"
    packaged_version_file.parent.mkdir(parents=True, exist_ok=True)
    packaged_version_file.write_text(json.dumps(version, indent=2), encoding="utf-8")
    env["VCB_VERSION_FILE"] = str(packaged_version_file)
    try:
        if not args.skip_tests:
            run_logged([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, log=failure_log, timeout=args.timeout, env=env)
        command = build_command(ROOT / "packaging" / "VAClaimBuilder.spec", staging_dist, work, verbose=args.verbose or args.diagnostic)
        build_seconds = run_logged(command, cwd=ROOT, log=failure_log, timeout=args.timeout, env=env)
        app = staging_dist / "VA Claim Builder.app"
        if args.platform == "macos" and not app.is_dir():
            raise RuntimeError(f"PyInstaller completed without producing {app}")
        pending.mkdir(parents=True)
        if app.exists():
            shutil.copytree(app, pending / app.name, symlinks=True)
            if args.adhoc_sign:
                run_logged(["codesign", "--force", "--deep", "--sign", "-", str(pending / app.name)], cwd=ROOT, log=failure_log, timeout=120)
            archive = pending / f"{app.stem}-{version['display_version'].replace(' ', '-')}-{platform.machine()}.zip"
            run_logged(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(pending / app.name), str(archive)], cwd=ROOT, log=failure_log, timeout=300)
        else:
            collection = staging_dist / "VAClaimBuilder"
            if not collection.exists():
                raise RuntimeError("PyInstaller completed without producing an application collection")
            shutil.copytree(collection, pending / collection.name, symlinks=True)
            if args.platform in {"windows", "portable"}:
                suffix = "Windows-x64" if args.platform == "windows" else f"portable-{machine}"
                archive_name = f"VA Claim Builder-{version['display_version'].replace(' ', '-')}-{suffix}"
                shutil.make_archive(str(pending / archive_name), "zip", pending, collection.name)
        report = {"architecture": architecture_report(), "dependencies": dependency_report()}
        (pending / "dependency-versions.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        shutil.copy2(failure_log, pending / "build.log")
        artifacts = [path for path in pending.iterdir() if path.is_file() and path.name not in {"release-manifest.json", "SHA256SUMS.txt"}]
        manifest = {
            "application": "VA Claim Builder", "version": version["version"], "display_version": version["display_version"],
            "target": args.platform, "built_at": datetime.now(timezone.utc).isoformat(), "build_seconds": round(build_seconds, 3),
            **architecture_report(), "signing": "ad-hoc" if args.adhoc_sign else "unsigned", "notarized": False,
            "artifacts": [{"name": path.name, "size": path.stat().st_size, "sha256": checksum(path)} for path in artifacts],
        }
        (pending / "release-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (pending / "SHA256SUMS.txt").write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in manifest["artifacts"]), encoding="utf-8")
        if final.exists():
            previous = output_root / f"{final.name}.previous-{stamp}"
            final.replace(previous)
        pending.replace(final)
        print(f"Release output: {final}")
        print(f"Total elapsed: {time.monotonic() - started:.1f}s")
        return 0
    except Exception as exc:
        shutil.rmtree(pending, ignore_errors=True)
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        if not args.keep_work:
            shutil.rmtree(build_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
