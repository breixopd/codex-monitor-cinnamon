#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UUID=codex-monitor@breixopd
ARCHIVE="$ROOT/dist/$UUID.zip"
SPICE_ARCHIVE="$ROOT/dist/$UUID-spices.zip"

python3 "$ROOT/scripts/validate.py"
python3 "$ROOT/scripts/package_spice.py" --archive-output "$ROOT/dist"
unzip -tq "$ARCHIVE"
unzip -tq "$SPICE_ARCHIVE"
