
# RC4 Windows NumPy Startup Correction

## Confirmed packaging defect

RC4 did not declare NumPy as a runtime dependency and explicitly excluded `numpy`
from the PyInstaller analysis. A build environment could still expose NumPy
transitively, allowing an incomplete namespace-like package to be analyzed while
its compiled runtime and DLLs were omitted. The installed application could then
resolve `numpy` but fail at startup because `numpy.ndarray` and
`numpy.core._multiarray_umath` were unavailable.

The repository contains no application-level `numpy.py` file or `numpy/`
directory that shadows the installed package.

## Correction

- Pin the Python 3.12-compatible `numpy==2.2.6` Windows x64 wheel.
- Remove NumPy from PyInstaller exclusions.
- Allow the standard PyInstaller NumPy hook to run.
- Collect NumPy dynamic libraries and the `_multiarray_umath` extension.
- Run dependency preflight before freezing.
- Inventory frozen NumPy DLL and `.pyd` files.
- Launch the actual packaged executable in diagnostic, UI, and synthetic intake
  modes before uploading the replacement artifact.

The correction does not add application functionality or scientific packages.
