#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UUID=codex-monitor@breixopd
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
TARGET_ROOT="$DATA_HOME/cinnamon/applets"
TARGET="$TARGET_ROOT/$UUID"
SCREENSHOT_DIR=${CODEX_MONITOR_SCREENSHOT_DIR:-/tmp/codex-monitor-smoke}
STARTED_AT=$(date --iso-8601=seconds)

eval_cinnamon() {
  result=$(gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
    --method org.Cinnamon.Eval "$1")
  case "$result" in
    "(true,"*) printf '%s\n' "$result" ;;
    *)
      printf '%s\n' "Cinnamon evaluation failed: $result" >&2
      return 1
      ;;
  esac
}

cleanup_smoke() {
  eval_cinnamon 'delete global._codexMonitorSmokeErrorIndex; "cleared";' >/dev/null 2>&1 || true
}
trap cleanup_smoke EXIT HUP INT TERM
eval_cinnamon 'global._codexMonitorSmokeErrorIndex=imports.ui.main._errorLogStack.length; "recorded";' >/dev/null

sh "$ROOT/scripts/install.sh"

copy_count=$(find "$TARGET_ROOT" -mindepth 1 -maxdepth 1 -name "$UUID*" -print | wc -l)
if [ "$copy_count" -ne 1 ]; then
  printf '%s\n' "Expected one discoverable Codex Monitor copy, found $copy_count" >&2
  exit 1
fi

gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.ReloadXlet "$UUID" APPLET >/dev/null
running=''
attempt=0
while [ "$attempt" -lt 20 ]; do
  running=$(gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
    --method org.Cinnamon.GetRunningXletUUIDs applet)
  case "$running" in
    *"$UUID"*) break ;;
  esac
  attempt=$((attempt + 1))
  sleep 1
done
case "$running" in
  *"$UUID"*) ;;
  *)
    printf '%s\n' "Codex Monitor is installed but is not enabled on a panel" >&2
    exit 1
    ;;
esac

geometry_js='var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; var a=x._fiveHourBar; var b=x._weeklyBar; var g1=a.x-(x._fiveHourLabel.x+x._fiveHourLabel.width); var g2=b.x-(x._weeklyLabel.x+x._weeklyLabel.width); var sn=x._dashboardScroll.get_theme_node(); var dn=x._dashboard.actor.get_theme_node(); JSON.stringify({instance:Boolean(x),snapshot:Boolean(x._snapshot),bridge:Boolean(x._bridge),centered:Math.abs((x._panelUsage.y+x._panelUsage.height/2)-x._panelBox.height/2)<=2,equalBars:a.width===b.width,equalGaps:Math.abs(g1-g2)<=1,viewportClipped:x._dashboardScroll.get_clip_to_allocation(),viewportBounded:x._dashboardScroll.height<=780,naturalContent:x._dashboard.actor.height>x._dashboardScroll.height,viewportPadding:sn.get_padding(imports.gi.St.Side.LEFT)===14&&sn.get_padding(imports.gi.St.Side.RIGHT)===14,contentUnpadded:dn.get_padding(imports.gi.St.Side.LEFT)===0&&dn.get_padding(imports.gi.St.Side.RIGHT)===0});'
geometry=''
attempt=0
while [ "$attempt" -lt 20 ]; do
  if geometry=$(eval_cinnamon "$geometry_js" 2>/dev/null) && \
      printf '%s\n' "$geometry" | grep -E 'snapshot.*true' >/dev/null; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
for assertion in instance snapshot bridge centered equalBars equalGaps viewportClipped viewportBounded naturalContent viewportPadding contentUnpadded; do
  if ! printf '%s\n' "$geometry" | grep -E "$assertion.*true" >/dev/null; then
    printf '%s\n' "Panel geometry assertion failed: $geometry" >&2
    exit 1
  fi
done

python3 "$ROOT/scripts/smoke_bridge.py" \
  --helper "$TARGET/helper/bridge.py" \
  --codex "${CODEX_BINARY:-codex}"

eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; x._readRemoteStatus(); "refreshing";' >/dev/null

dashboard_js='var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; var modes=["quota","activity","both"]; var ranges=[24,168,720]; for (var i=0;i<modes.length;i++){for(var j=0;j<ranges.length;j++){x.graphMode=modes[i];x.graphRangeHours=ranges[j];x._render();}} x.menu.open(); var graph=x._dashboard._graphActor; var labels=graph._xAxis.get_children().map(function(v){return v.get_text();}); var legend=graph._legend.get_children().map(function(v){return v.get_text();}); var hoverStart=graph._hoverFormatter(graph._area._minimum); var hoverEnd=graph._hoverFormatter(graph._area._maximum); JSON.stringify({legendReady:legend.length>0,compactLegend:legend.length<=3&&legend.every(function(v){return v.indexOf(" min ")<0&&v.indexOf(" max ")<0&&v.indexOf("now —")<0;}),hoverDates:hoverStart!==hoverEnd,nativeQr:Boolean(x._dashboard._pairingQr),axisReady:labels.every(function(v){return Boolean(v)&&v!=="—";}),sessions:Boolean(x._dashboard._activeSessionList&&x._dashboard._recentSessionList),remote:Boolean(x._dashboard._remoteClientList),requestGuards:Boolean("_remoteRefreshing" in x&&"_pairingPolling" in x&&"_clientsLoading" in x)});'
dashboard=$(eval_cinnamon "$dashboard_js")
for assertion in legendReady compactLegend hoverDates nativeQr axisReady sessions remote requestGuards; do
  if ! printf '%s\n' "$dashboard" | grep -E "$assertion.*true" >/dev/null; then
    printf '%s\n' "Dashboard assertion failed: $dashboard" >&2
    exit 1
  fi
done

remote_before=$(eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; String(x._remoteStatus&&x._remoteStatus.status||"unknown");')
matrix_js=$(tr '\n' ' ' < "$ROOT/scripts/live-matrix.js")
matrix=$(eval_cinnamon "$matrix_js")
for assertion in instance graphMatrix emptyGraph singleGraph gapGraph foreignQuotaFiltered sparseQuotaFitted denseGraph peakGraph quotaUnavailable quotaNormal quotaWarning quotaCritical staleCritical resetNormal resetWarning resetCritical remoteDisabled remoteConnecting remoteConnected remoteError qrAvailable qrFallback pairingClaimed pairingExpired updateCurrent updateAvailable updateChecking updateUpdating updateUpdated updateFailed sessionsEmpty sessionsActiveRecent sessionsUnavailable; do
  if ! printf '%s\n' "$matrix" | grep -E "$assertion.*true" >/dev/null; then
    printf '%s\n' "Dynamic visual matrix assertion failed ($assertion): $matrix" >&2
    exit 1
  fi
done
if printf '%s\n' "$matrix" | grep -E 'matrixException.*true' >/dev/null; then
  printf '%s\n' "Dynamic visual matrix raised an exception: $matrix" >&2
  exit 1
fi
remote_after=$(eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; String(x._remoteStatus&&x._remoteStatus.status||"unknown");')
remoteStatePreserved=false
if [ "$remote_before" = "$remote_after" ]; then
  remoteStatePreserved=true
fi
if [ "$remoteStatePreserved" != true ]; then
  printf '%s\n' "Remote state changed during visual matrix" >&2
  exit 1
fi

settled_js='var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; var quotaReady=x._dashboard._fiveHourCard._percent.get_text().indexOf("%")>=0||x._dashboard._weeklyCard._percent.get_text().indexOf("%")>=0; JSON.stringify({settledQuota:Boolean(x._snapshot&&x._dashboard._snapshot===x._snapshot&&quotaReady),settledSessions:Boolean(x._sessions&&x._dashboard._sessions===x._sessions),settledRemote:Boolean(x._remoteStatus&&["disabled","connecting","connected"].indexOf(x._remoteStatus.status)>=0)});'
settled=''
attempt=0
while [ "$attempt" -lt 20 ]; do
  settled=$(eval_cinnamon "$settled_js")
  if printf '%s\n' "$settled" | grep -E 'settledQuota.*true' >/dev/null && \
      printf '%s\n' "$settled" | grep -E 'settledSessions.*true' >/dev/null && \
      printf '%s\n' "$settled" | grep -E 'settledRemote.*true' >/dev/null; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
for assertion in settledQuota settledSessions settledRemote; do
  if ! printf '%s\n' "$settled" | grep -E "$assertion.*true" >/dev/null; then
    printf '%s\n' "Dashboard readiness assertion failed: $settled" >&2
    exit 1
  fi
done

# Allow the next Cinnamon paint to commit the verified actor state to the frame.
sleep 1

mkdir -p "$SCREENSHOT_DIR"
gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.Screenshot false false "$SCREENSHOT_DIR/dashboard.png" >/dev/null
eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; x.menu.close(); "closed";' >/dev/null
gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.Screenshot false false "$SCREENSHOT_DIR/panel.png" >/dev/null

if journalctl --user -b --since "$STARTED_AT" --no-pager -o cat | \
  rg -i 'codex-monitor.*(error|exception|traceback)|(error|exception|traceback).*codex-monitor' >/dev/null; then
  printf '%s\n' "Cinnamon logged a Codex Monitor error during live smoke" >&2
  exit 1
fi

looking_glass=$(eval_cinnamon 'var start=Number(global._codexMonitorSmokeErrorIndex||0); var errors=imports.ui.main._errorLogStack.slice(start).filter(function(item){var message=String(item.message||"").toLowerCase();return ["error","trace"].indexOf(item.category)>=0&&message.indexOf("codex-monitor@breixopd")>=0;}); JSON.stringify({lookingGlassClean:errors.length===0});')
if ! printf '%s\n' "$looking_glass" | grep -E 'lookingGlassClean.*true' >/dev/null; then
  printf '%s\n' "Cinnamon LookingGlass recorded a Codex Monitor error" >&2
  exit 1
fi

printf '%s\n' "Live smoke passed; screenshots: $SCREENSHOT_DIR"
