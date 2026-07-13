#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UUID=codex-monitor@breixopd
ARCHIVE="$ROOT/dist/$UUID.zip"

python3 "$ROOT/scripts/validate.py"
mkdir -p "$ROOT/dist"
(
  cd "$ROOT/files"
  zip -FSqr "$ARCHIVE" "$UUID" \
    -x '*/__pycache__/*' '*.pyc' '*.pyo'
)
unzip -tq "$ARCHIVE"
printf '%s\n' "Built $ARCHIVE"
