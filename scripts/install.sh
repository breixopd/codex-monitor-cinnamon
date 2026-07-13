#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UUID=codex-monitor@breixopd
SOURCE="$ROOT/files/$UUID"
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
TARGET_ROOT="$DATA_HOME/cinnamon/applets"
TARGET="$TARGET_ROOT/$UUID"
LEGACY_BACKUP_ROOT="$DATA_HOME/$UUID/install-backups"

if [ ! -f "$SOURCE/metadata.json" ]; then
  printf '%s\n' "Applet source not found at $SOURCE" >&2
  exit 1
fi

mkdir -p "$TARGET_ROOT"
rm -rf -- "$LEGACY_BACKUP_ROOT"
for stale in "$TARGET_ROOT/$UUID".backup-[0-9]*; do
  [ -e "$stale" ] || continue
  rm -rf -- "$stale"
done
STAGING=$(mktemp -d "$TARGET_ROOT/.codex-monitor.XXXXXX")
PREVIOUS=
cleanup() {
  rm -rf -- "$STAGING"
  if [ -n "$PREVIOUS" ] && [ -e "$PREVIOUS" ]; then
    if [ ! -e "$TARGET" ]; then
      mv "$PREVIOUS" "$TARGET"
    else
      rm -rf -- "$PREVIOUS"
    fi
  fi
}
trap cleanup EXIT HUP INT TERM
cp -a "$SOURCE/." "$STAGING/"

if [ -e "$TARGET" ]; then
  PREVIOUS=$(mktemp -d "$TARGET_ROOT/.codex-monitor.previous.XXXXXX")
  rmdir "$PREVIOUS"
  mv "$TARGET" "$PREVIOUS"
fi
mv "$STAGING" "$TARGET"
if [ -n "$PREVIOUS" ]; then
  rm -rf -- "$PREVIOUS"
  PREVIOUS=
fi
trap - EXIT HUP INT TERM

printf '%s\n' "Installed Codex Monitor at $TARGET"
printf '%s\n' "Open System Settings > Applets and add Codex Monitor to a panel."
