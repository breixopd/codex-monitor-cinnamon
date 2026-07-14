#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UUID=codex-monitor@breixopd
WORK_DIR=/tmp/codex-monitor-store-screenshot
CAPTURE="$WORK_DIR/screenshot.png"

eval_cinnamon() {
  phase=${2:-Cinnamon}
  result=$(gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
    --method org.Cinnamon.Eval "$1")
  case "$result" in
    "(true,"*) printf '%s\n' "$result" ;;
    *)
      printf '%s\n' "$phase evaluation failed: $result" >&2
      return 1
      ;;
  esac
}

cleanup_store_capture() {
  eval_cinnamon 'if(global._codexMonitorDestroyScreenshotScene) global._codexMonitorDestroyScreenshotScene(); "destroyed";' >/dev/null 2>&1 || true
  rm -rf -- "$WORK_DIR"
}
trap cleanup_store_capture EXIT HUP INT TERM

command -v gdbus >/dev/null

rm -rf -- "$WORK_DIR"
mkdir -p "$WORK_DIR"
sh "$ROOT/scripts/install.sh" >/dev/null
gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.ReloadXlet "$UUID" APPLET >/dev/null

attempt=0
instance_state=
while [ "$attempt" -lt 60 ]; do
  instance_state=$(eval_cinnamon '(function(){var instances=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd"); return instances.length>0?"instance-ready":"loading";})()')
  case "$instance_state" in
    *instance-ready*) break ;;
  esac
  attempt=$((attempt + 1))
  sleep 0.5
done
case "$instance_state" in
  *instance-ready*) ;;
  *)
    printf '%s\n' "Codex Monitor did not finish loading after Cinnamon reloaded it." >&2
    exit 1
    ;;
esac

scene_js=$(tr '\n' ' ' < "$ROOT/scripts/store-screenshot-scene.js")
scene_wrapper="(function(){try{return $scene_js;}catch(error){return JSON.stringify({ready:false,error:String(error),line:error.lineNumber||null});}})()"
scene_state=$(eval_cinnamon "$scene_wrapper" "Scene")
case "$scene_state" in
  *'\\"ready\\":true'*) ;;
  *)
    printf '%s\n' "Could not create the isolated screenshot scene: $scene_state" >&2
    exit 1
    ;;
esac

sleep 2
scene_probe=$(eval_cinnamon 'global._codexMonitorScreenshotScene&&global._codexMonitorScreenshotScene.root?"scene-present":"scene-missing";' "Scene probe")
case "$scene_probe" in
  *scene-present*) ;;
  *)
    printf '%s\n' "The isolated screenshot scene disappeared before capture." >&2
    exit 1
    ;;
esac
x=20
y=20
width=1300
height=880

gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.ScreenshotArea false "$x" "$y" "$width" "$height" \
  false "$CAPTURE" >/dev/null
attempt=0
while [ ! -s "$CAPTURE" ] && [ "$attempt" -lt 30 ]; do
  attempt=$((attempt + 1))
  sleep 0.1
done
if [ ! -s "$CAPTURE" ]; then
  printf '%s\n' "Cinnamon did not capture the isolated screenshot scene." >&2
  exit 1
fi
mv "$CAPTURE" "$ROOT/store/screenshot.png"
cleanup_store_capture
trap - EXIT HUP INT TERM
printf '%s\n' "Updated $ROOT/store/screenshot.png from the isolated demo scene."
