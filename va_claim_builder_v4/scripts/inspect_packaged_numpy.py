from __future__ import annotations

import argparse
import json
import platform
import struct
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory NumPy files in a frozen Windows application.")
    parser.add_argument("application", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.application.resolve()
    numpy_files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ("numpy" in path.as_posix().lower() or path.suffix.lower() in {".pyd", ".dll"})
    )
    report = {
        "passed": any("_multiarray_umath" in name for name in numpy_files),
        "host_machine": platform.machine(),
        "host_bits": struct.calcsize("P") * 8,
        "application": str(root),
        "numpy_file_count": sum("numpy" in name.lower() for name in numpy_files),
        "compiled_extension_count": sum(name.lower().endswith(".pyd") for name in numpy_files),
        "dll_count": sum(name.lower().endswith(".dll") for name in numpy_files),
        "files": numpy_files,
    }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
