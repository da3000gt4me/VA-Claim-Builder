from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import struct
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dependencies required before freezing VA Claim Builder.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import numpy
    import numpy.core._multiarray_umath
    import cryptography
    import pypdf

    assert numpy.ndarray is not None
    report = {
        "passed": True,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "python_bits": struct.calcsize("P") * 8,
        "machine": platform.machine(),
        "numpy_version": importlib.metadata.version("numpy"),
        "numpy_file": numpy.__file__,
        "numpy_spec": repr(numpy.__spec__),
        "numpy_ndarray_available": True,
        "numpy_multiarray_imported": True,
        "cryptography_version": importlib.metadata.version("cryptography"),
        "pypdf_version": importlib.metadata.version("pypdf"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
