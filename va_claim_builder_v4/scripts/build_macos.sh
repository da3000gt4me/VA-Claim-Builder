#!/bin/sh
set -eu
python3 "$(dirname "$0")/build_release.py" macos --clean
