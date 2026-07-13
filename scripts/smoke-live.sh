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

json_true() {
  printf '%s\n' "$1" | grep -F "\\\\\"$2\\\\\":true" >/dev/null
}

wait_for_screenshot() {
  screenshot_path=$1
  screenshot_attempt=0
  while [ ! -s "$screenshot_path" ] && [ "$screenshot_attempt" -lt 20 ]; do
    screenshot_attempt=$((screenshot_attempt + 1))
    sleep 0.1
  done
  [ -s "$screenshot_path" ]
}

cleanup_smoke() {
  eval_cinnamon 'var instances=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd"); var x=instances&&instances[0]; if(x&&global._codexMonitorHoverMode!==undefined){x.graphMode=global._codexMonitorHoverMode;x.graphRangeHours=global._codexMonitorHoverRange;x._render();} var old=global._codexMonitorHoverPointer; if(old) imports.gi.Clutter.get_default_backend().get_default_seat().warp_pointer(old[0],old[1]); delete global._codexMonitorSmokeErrorIndex; delete global._codexMonitorOldInstance; delete global._codexMonitorOldBridge; delete global._codexMonitorOldSnapshot; delete global._codexMonitorHoverPointer; delete global._codexMonitorHoverLeft; delete global._codexMonitorHoverDetail; delete global._codexMonitorHoverMode; delete global._codexMonitorHoverRange; "cleared";' >/dev/null 2>&1 || true
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

geometry_js='var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; var a=x._fiveHourBar; var b=x._weeklyBar; var g1=a.x-(x._fiveHourLabel.x+x._fiveHourLabel.width); var g2=b.x-(x._weeklyLabel.x+x._weeklyLabel.width); var sn=x._dashboardScroll.get_theme_node(); var dn=x._dashboard.actor.get_theme_node(); JSON.stringify({instance:Boolean(x),snapshot:Boolean(x._snapshot),bridge:Boolean(x._bridge),centered:Math.abs((x._panelUsage.y+x._panelUsage.height/2)-x._panelBox.height/2)<=2,equalBars:a.width===b.width,equalGaps:Math.abs(g1-g2)<=1,viewportClipped:x._dashboardScroll.get_clip_to_allocation(),viewportBounded:x._dashboardScroll.height<=780,naturalContent:x._dashboard.actor.height>x._dashboardScroll.height,viewportPadding:sn.get_padding(imports.gi.St.Side.LEFT)===14&&sn.get_padding(imports.gi.St.Side.RIGHT)===14,contentUnpadded:dn.get_padding(imports.gi.St.Side.LEFT)===0&&dn.get_padding(imports.gi.St.Side.RIGHT)===0,reservedScrollbar:x._dashboardScroll.overlay_scrollbars===false});'
geometry=''
attempt=0
while [ "$attempt" -lt 20 ]; do
  if geometry=$(eval_cinnamon "$geometry_js" 2>/dev/null) && \
      json_true "$geometry" snapshot; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
for assertion in instance snapshot bridge centered equalBars equalGaps viewportClipped viewportBounded naturalContent viewportPadding contentUnpadded reservedScrollbar; do
  if ! json_true "$geometry" "$assertion"; then
    printf '%s\n' "Panel geometry assertion failed: $geometry" >&2
    exit 1
  fi
done

# Reload the newly installed code once more so this run exercises its own
# removal callback, not only the previously installed version's callback.
eval_cinnamon 'global._codexMonitorOldInstance=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; "marked";' >/dev/null
gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.ReloadXlet "$UUID" APPLET >/dev/null
lifecycle_removal=''
attempt=0
while [ "$attempt" -lt 20 ]; do
  lifecycle_removal=$(eval_cinnamon 'var old=global._codexMonitorOldInstance; var current=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; JSON.stringify({lifecycleRemovalClean:Boolean(old&&old._destroyed&&old._bridge===null&&current&&current!==old&&current._bridge&&current._snapshot)});')
  if json_true "$lifecycle_removal" lifecycleRemovalClean; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
if ! json_true "$lifecycle_removal" lifecycleRemovalClean; then
  printf '%s\n' "Applet removal lifecycle assertion failed: $lifecycle_removal" >&2
  exit 1
fi
eval_cinnamon 'delete global._codexMonitorOldInstance; "cleared";' >/dev/null

# Restart only the helper and require a fresh snapshot. This catches callbacks
# from the retired helper mutating flags or scheduling a delayed second restart.
eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; global._codexMonitorOldBridge=x._bridge; global._codexMonitorOldSnapshot=x._snapshot; x._configurationChanged(); "restarting";' >/dev/null
lifecycle_restart=''
attempt=0
while [ "$attempt" -lt 20 ]; do
  lifecycle_restart=$(eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; JSON.stringify({lifecycleRestartClean:Boolean(x&&x._bridge&&x._bridge!==global._codexMonitorOldBridge&&x._snapshot&&x._snapshot!==global._codexMonitorOldSnapshot&&!x._refreshing&&x._restartTimer===0)});')
  if json_true "$lifecycle_restart" lifecycleRestartClean; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
if ! json_true "$lifecycle_restart" lifecycleRestartClean; then
  printf '%s\n' "Bridge restart lifecycle assertion failed: $lifecycle_restart" >&2
  exit 1
fi
eval_cinnamon 'delete global._codexMonitorOldBridge; delete global._codexMonitorOldSnapshot; "cleared";' >/dev/null

python3 "$ROOT/scripts/smoke_bridge.py" \
  --helper "$TARGET/helper/bridge.py" \
  --codex "${CODEX_BINARY:-codex}"

eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; x._readRemoteStatus(); "refreshing";' >/dev/null

dashboard_js='var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; x.menu.open(); var graph=x._dashboard._graphActor; var labels=graph._xAxis.get_children().map(function(v){return v.get_text();}); var legend=graph._legend.get_children().map(function(v){return v.get_text();}); var hoverStart=graph._hoverFormatter(graph._area._minimum); var hoverEnd=graph._hoverFormatter(graph._area._maximum); JSON.stringify({legendReady:legend.length>0,compactLegend:legend.length<=3&&legend.every(function(v){return v.indexOf(" min ")<0&&v.indexOf(" max ")<0&&v.indexOf("now —")<0;}),hoverDates:hoverStart!==hoverEnd,nativeQr:Boolean(x._dashboard._pairingQr),axisReady:labels.every(function(v){return Boolean(v)&&v!=="—";}),sessions:Boolean(x._dashboard._activeSessionList&&x._dashboard._recentSessionList),remote:Boolean(x._dashboard._remoteClientList),requestGuards:Boolean("_remoteRefreshing" in x&&"_pairingPolling" in x&&"_clientsLoading" in x)});'
dashboard=$(eval_cinnamon "$dashboard_js")
for assertion in legendReady compactLegend hoverDates nativeQr axisReady sessions remote requestGuards; do
  if ! json_true "$dashboard" "$assertion"; then
    printf '%s\n' "Dashboard assertion failed: $dashboard" >&2
    exit 1
  fi
done

# Exercise Cinnamon's actual pointer-event path in every mode and range. Calling
# the formatter directly would miss allocation/event bugs in the reactive actor.
eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; global._codexMonitorHoverPointer=global.get_pointer().slice(0,2); global._codexMonitorHoverMode=x.graphMode; global._codexMonitorHoverRange=x.graphRangeHours; "hover-saved";' >/dev/null
for hover_mode in quota activity both; do
  for hover_range in 24 168 720; do
    eval_cinnamon "var x=imports.ui.appletManager.getRunningInstancesForUuid(\"codex-monitor@breixopd\")[0]; x.graphMode=\"$hover_mode\"; x.graphRangeHours=$hover_range; x._render(); x.menu.open(); var a=x._dashboard._graphActor._area; var p=a.get_transformed_position(); imports.gi.Clutter.get_default_backend().get_default_seat().warp_pointer(Math.round(p[0]+12),Math.round(p[1]+a.height/2)); \"hover-left\";" >/dev/null
    sleep 0.2
    eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; var g=x._dashboard._graphActor; var a=g._area; var p=a.get_transformed_position(); global._codexMonitorHoverLeft=a._hoverTimestamp; global._codexMonitorHoverDetail=g._hover.get_text(); imports.gi.Clutter.get_default_backend().get_default_seat().warp_pointer(Math.round(p[0]+a.width-12),Math.round(p[1]+a.height/2)); "hover-right";' >/dev/null
    sleep 0.2
    hover_result=$(eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; var g=x._dashboard._graphActor; var a=g._area; var left=Number(global._codexMonitorHoverLeft); var right=Number(a._hoverTimestamp); var span=a._maximum-a._minimum; JSON.stringify({hoverTracksPointer:Number.isFinite(left)&&Number.isFinite(right)&&right-left>span*0.75,hoverDetailChanges:g._hover.get_text()!==global._codexMonitorHoverDetail});')
    for assertion in hoverTracksPointer hoverDetailChanges; do
      if ! json_true "$hover_result" "$assertion"; then
        printf '%s\n' "Graph pointer assertion failed ($hover_mode/$hover_range): $hover_result" >&2
        exit 1
      fi
    done
  done
done
eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; x.graphMode=global._codexMonitorHoverMode; x.graphRangeHours=global._codexMonitorHoverRange; x._render(); var old=global._codexMonitorHoverPointer; if(old) imports.gi.Clutter.get_default_backend().get_default_seat().warp_pointer(old[0],old[1]); delete global._codexMonitorHoverPointer; delete global._codexMonitorHoverLeft; delete global._codexMonitorHoverDetail; delete global._codexMonitorHoverMode; delete global._codexMonitorHoverRange; "hover-restored";' >/dev/null

remote_before=$(eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; String(x._remoteStatus&&x._remoteStatus.status||"unknown");')
matrix_js=$(tr '\n' ' ' < "$ROOT/scripts/live-matrix.js")
matrix=$(eval_cinnamon "$matrix_js")
for assertion in instance graphMatrix emptyGraph singleGraph gapGraph foreignQuotaFiltered sparseQuotaFullRange denseGraph peakGraph quotaUnavailable quotaNormal quotaWarning quotaCritical staleCritical resetNormal resetWarning resetCritical remoteDisabled remoteConnecting remoteRunning remoteConnected remoteError qrAvailable qrFallback pairingClaimed pairingExpired updateCurrent updateAvailable updateChecking updateUpdating updateUpdated updateFailed sessionsEmpty sessionsActiveRecent sessionsUnavailable; do
  if ! json_true "$matrix" "$assertion"; then
    printf '%s\n' "Dynamic visual matrix assertion failed ($assertion): $matrix" >&2
    exit 1
  fi
done
if json_true "$matrix" matrixException; then
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
  if json_true "$settled" settledQuota && \
      json_true "$settled" settledSessions && \
      json_true "$settled" settledRemote; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done
for assertion in settledQuota settledSessions settledRemote; do
  if ! json_true "$settled" "$assertion"; then
    printf '%s\n' "Dashboard readiness assertion failed: $settled" >&2
    exit 1
  fi
done

mkdir -p "$SCREENSHOT_DIR"
rm -f -- "$SCREENSHOT_DIR/dashboard.png" "$SCREENSHOT_DIR/panel.png"
dashboard_capture=$(eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; x.menu.open(); JSON.stringify({dashboardCaptureReady:Boolean(x.menu.isOpen&&x._dashboardScroll.mapped)});')
if ! json_true "$dashboard_capture" dashboardCaptureReady; then
  printf '%s\n' "Dashboard capture did not open the popup: $dashboard_capture" >&2
  exit 1
fi
# Allow the popup animation and two Cinnamon paints to settle.
sleep 2
dashboard_capture=$(eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; var v=x._dashboardScroll.get_vscroll_bar(); var d=x._dashboard.actor; var status=x._dashboard._status; var statusNode=status.get_theme_node(); var statusMargins=statusNode.get_margin(imports.gi.St.Side.LEFT)+statusNode.get_margin(imports.gi.St.Side.RIGHT); JSON.stringify({dashboardCaptureReady:Boolean(x.menu.isOpen&&x._dashboardScroll.mapped),contentClearOfScrollbar:Boolean(d.x+d.width<=v.x),headerClearOfScrollbar:Boolean(d.x+status.x+status.width+statusMargins<=v.x),headerStatusFits:Boolean(status.width+statusMargins>=status.get_preferred_width(-1)[1])});')
if ! json_true "$dashboard_capture" dashboardCaptureReady || \
    ! json_true "$dashboard_capture" contentClearOfScrollbar || \
    ! json_true "$dashboard_capture" headerClearOfScrollbar || \
    ! json_true "$dashboard_capture" headerStatusFits; then
  printf '%s\n' "Dashboard geometry changed before capture: $dashboard_capture" >&2
  exit 1
fi
gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.Screenshot false false "$SCREENSHOT_DIR/dashboard.png" >/dev/null
if ! wait_for_screenshot "$SCREENSHOT_DIR/dashboard.png"; then
  printf '%s\n' "Dashboard screenshot was not created" >&2
  exit 1
fi
# Cinnamon creates the file before the compositor has finished sampling it.
sleep 5
eval_cinnamon 'var x=imports.ui.appletManager.getRunningInstancesForUuid("codex-monitor@breixopd")[0]; x.menu.close(); "closed";' >/dev/null
# Let the close animation finish before capturing the panel-only state.
sleep 2
gdbus call --session --dest org.Cinnamon --object-path /org/Cinnamon \
  --method org.Cinnamon.Screenshot false false "$SCREENSHOT_DIR/panel.png" >/dev/null
if ! wait_for_screenshot "$SCREENSHOT_DIR/panel.png"; then
  printf '%s\n' "Panel screenshot was not created" >&2
  exit 1
fi

if journalctl --user -b --since "$STARTED_AT" --no-pager -o cat | \
  rg -i 'codex-monitor.*(error|exception|traceback)|(error|exception|traceback).*codex-monitor' >/dev/null; then
  printf '%s\n' "Cinnamon logged a Codex Monitor error during live smoke" >&2
  exit 1
fi

looking_glass=$(eval_cinnamon 'var start=Number(global._codexMonitorSmokeErrorIndex||0); var errors=imports.ui.main._errorLogStack.slice(start).filter(function(item){var message=String(item.message||"").toLowerCase();return ["error","trace"].indexOf(item.category)>=0&&message.indexOf("codex-monitor@breixopd")>=0;}); JSON.stringify({lookingGlassClean:errors.length===0});')
if ! json_true "$looking_glass" lookingGlassClean; then
  printf '%s\n' "Cinnamon LookingGlass recorded a Codex Monitor error" >&2
  exit 1
fi

printf '%s\n' "Live smoke passed; screenshots: $SCREENSHOT_DIR"
