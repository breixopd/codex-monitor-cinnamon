#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UUID=codex-monitor@breixopd
SOURCE="$ROOT/files/$UUID"
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
TARGET_ROOT="$DATA_HOME/cinnamon/applets"
TARGET="$TARGET_ROOT/$UUID"
BACKUP_ROOT="$DATA_HOME/$UUID/install-backups"

if [ ! -f "$SOURCE/metadata.json" ]; then
  printf '%s\n' "Applet source not found at $SOURCE" >&2
  exit 1
fi

mkdir -p "$TARGET_ROOT" "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
for stale in "$TARGET_ROOT/$UUID".backup-[0-9]*; do
  [ -e "$stale" ] || continue
  rm -rf -- "$stale"
done
STAGING=$(mktemp -d "$TARGET_ROOT/.codex-monitor.XXXXXX")
cleanup() {
  rm -rf "$STAGING"
}
trap cleanup EXIT HUP INT TERM
cp -a "$SOURCE/." "$STAGING/"

if [ -e "$TARGET" ]; then
  BACKUP="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)-$$"
  mv "$TARGET" "$BACKUP"
  printf '%s\n' "Previous installation saved at $BACKUP"
fi
mv "$STAGING" "$TARGET"
trap - EXIT HUP INT TERM

printf '%s\n' "Installed Codex Monitor at $TARGET"
printf '%s\n' "Open System Settings > Applets and add Codex Monitor to a panel."
