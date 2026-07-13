#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UUID=codex-monitor@breixopd
ARCHIVE="$ROOT/dist/$UUID.zip"
SPICE_ROOT="$ROOT/dist/spices"
SPICE_ARCHIVE="$ROOT/dist/$UUID-spices.zip"

python3 "$ROOT/scripts/validate.py"
python3 "$ROOT/scripts/package_spice.py" --output "$SPICE_ROOT"
mkdir -p "$ROOT/dist"
(
  cd "$ROOT/files"
  zip -FSqr "$ARCHIVE" "$UUID" \
    -x '*/__pycache__/*' '*.pyc' '*.pyo'
)
unzip -tq "$ARCHIVE"
(
  cd "$SPICE_ROOT"
  zip -FSqr "$SPICE_ARCHIVE" "$UUID" \
    -x '*/__pycache__/*' '*.pyc' '*.pyo'
)
unzip -tq "$SPICE_ARCHIVE"
printf '%s\n' "Built $ARCHIVE"
printf '%s\n' "Built $SPICE_ARCHIVE"
