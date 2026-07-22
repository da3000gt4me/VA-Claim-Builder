#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
ENV_DIR=${VCB_BUILD_ENV:-"$ROOT/.build-env-macos"}
if [ ! -x "$ENV_DIR/bin/python" ]; then
  python3.12 -m venv "$ENV_DIR"
  "$ENV_DIR/bin/python" -m pip install --upgrade pip
  "$ENV_DIR/bin/python" -m pip install -r "$ROOT/requirements-packaging.txt"
fi
exec "$ENV_DIR/bin/python" "$ROOT/scripts/build_release.py" macos --clean "$@"
