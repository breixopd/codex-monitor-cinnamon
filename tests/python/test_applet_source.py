from pathlib import Path
import re


APPLET_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "files"
    / "codex-monitor@breixopd"
    / "applet.js"
)
UI_SOURCE = APPLET_SOURCE.with_name("ui.js")
STYLESHEET_SOURCE = APPLET_SOURCE.with_name("stylesheet.css")
GRAPH_SOURCE = APPLET_SOURCE.with_name("graph.js")
BRIDGE_CLIENT_SOURCE = APPLET_SOURCE.with_name("bridgeClient.js")


def _css_rule(source, selector):
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", source)
    assert match is not None
    return match.group(1)


def test_refresh_keeps_status_indicators_hidden_on_vertical_panels():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    assert "this._indicatorBox.visible = !vertical" in source


def test_panel_renders_normalized_indicator_actors_and_accessible_text():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    assert "state.indicators" in source
    assert "codex-indicator-${indicator.kind}" in source
    assert "codex-indicator-${indicator.severity}" in source
    assert "state.indicatorText" in source


def test_dashboard_explains_current_indicators_in_plain_language():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "Current indicators" in source
    assert "Usage data current" in source
    assert "setIndicators(indicators)" in source
    assert "set_line_wrap(true)" in source
    assert "Pango.EllipsizeMode.NONE" in source
    assert "codex-monitor-indicator-row" in source
    assert "indicator.kind === 'remote' ? '  ' : ' '" in source
    assert "${indicator.symbol}${indicatorGap}" in source


def test_dashboard_compact_layout_stacks_dense_rows_and_reflows_filters():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "setCompactLayout(compact)" in source
    assert "this._compact = false;" in source
    assert "const indicatorsPerRow = this._compact ? 1 : 2;" in source
    assert "const filtersPerRow = this._compact ? 2 : 4;" in source
    for actor in (
        "this._header",
        "this._quotaRow",
        "this._graphHeading",
        "this._sessionHeadingRow",
        "this._remoteHeading",
        "this._remoteClientsHeadingRow",
        "this._remoteButtons",
        "this._versionRow",
        "this._footer",
    ):
        assert f"{actor}.set_vertical(this._compact);" in source

    assert "vertical: this._compact" in source


def test_dashboard_width_is_runtime_responsive_and_keeps_scrollbar_gutter():
    stylesheet = STYLESHEET_SOURCE.read_text(encoding="utf-8")
    dashboard_rule = _css_rule(stylesheet, ".codex-monitor-dashboard")
    scrollbar_rule = _css_rule(
        stylesheet, ".codex-monitor-scroll StScrollBar"
    )

    assert "width:" not in dashboard_rule
    assert "margin-left: 12px" in scrollbar_rule


def test_dashboard_uses_active_monitor_work_area_and_reacts_to_layout_changes():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    assert "Main.layoutManager.findMonitorForActor(this.actor)" in source
    assert "global.screen.get_active_workspace()" in source
    assert "get_work_area_for_monitor(monitor.index)" in source
    assert "Model.responsiveLayout(workArea.width, workArea.height)" in source
    assert "this._dashboard.actor.set_width(layout.contentWidth);" in source
    assert "this._dashboard.setCompactLayout(layout.compact);" in source
    assert "open-state-changed" in source
    assert "monitors-changed" in source
    assert "this._updateDashboardLayout();" in source

    removal = source[source.index("on_applet_removed_from_panel()") :]
    assert "Main.layoutManager.disconnect(this._monitorsChangedId);" in removal


def test_indicator_severities_have_distinct_semantic_styles():
    source = STYLESHEET_SOURCE.read_text(encoding="utf-8")

    assert ".codex-indicator-warning" in source
    assert ".codex-indicator-critical" in source
    assert ".codex-indicator-success" in source
    assert ".codex-indicator-info" in source
    assert "#e8a641" in source
    assert "#e05a62" in source


def test_scroll_viewport_owns_padding_and_clips_the_moving_dashboard():
    applet = APPLET_SOURCE.read_text(encoding="utf-8")
    stylesheet = STYLESHEET_SOURCE.read_text(encoding="utf-8")
    dashboard_rule = _css_rule(stylesheet, ".codex-monitor-dashboard")
    scroll_rule = _css_rule(stylesheet, ".codex-monitor-scroll")
    menu_item_rule = _css_rule(
        stylesheet, ".popup-menu-item.codex-monitor-menu-item"
    )
    header_status_rule = _css_rule(
        stylesheet, ".codex-monitor-header .codex-monitor-status"
    )

    assert "padding" not in dashboard_rule
    assert "style_class: 'codex-monitor-menu-item'" in applet
    assert "padding-left: 0" in menu_item_rule
    assert "padding-right: 0" in menu_item_rule
    assert "margin-left: 0" in menu_item_rule
    assert "margin-right: 0" in menu_item_rule
    assert "padding: 16px 0 8px" in scroll_rule
    assert "max-height: 752px" in scroll_rule
    assert "set_clip_to_allocation(true)" in applet
    assert "overlay_scrollbars: false" in applet
    assert "width: 160px" in header_status_rule
    assert "margin-right: 8px" in header_status_rule
    assert "text-align: right" in header_status_rule


def test_retired_bridge_callbacks_cannot_restart_or_mutate_a_removed_applet():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    assert "this._destroyed = false;" in source
    assert "_request(action, params, callback)" in source
    assert "this._destroyed || bridge !== this._bridge" in source
    assert source.count("this._bridge.request(") == 0
    assert "_render() {\n    if (this._destroyed || !this._dashboard)" in source
    assert "_configurationChanged() {\n    if (this._destroyed || !this._dashboard)" in source

    removal = source[source.index("on_applet_removed_from_panel()") :]
    assert removal.index("this._destroyed = true;") < removal.index("bridge.stop();")
    assert removal.index("this._bridge = null;") < removal.index("bridge.stop();")


def test_bridge_shutdown_waits_for_helper_and_has_a_bounded_force_fallback():
    source = BRIDGE_CLIENT_SOURCE.read_text(encoding="utf-8")

    assert "if (this._process && this._running)" not in source
    assert "process.wait_async" in source
    assert "Mainloop.timeout_add_seconds(5" in source
    assert "process.force_exit()" in source


def test_remote_stop_is_confirmed_before_the_destructive_bridge_action():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    assert "onRemoteStop: this._confirmRemoteStop.bind(this)" in source
    assert "_confirmRemoteStop()" in source
    assert "this._remoteAction('remote_stop', { confirmed: true });" in source


def test_remote_device_management_exposes_distinct_live_states_and_retry_backoff():
    applet = APPLET_SOURCE.read_text(encoding="utf-8")
    ui = UI_SOURCE.read_text(encoding="utf-8")

    for message in (
        "Checking paired devices…",
        "Device channel is not responding; retrying automatically",
        "This Codex build does not expose device management",
        "No paired devices",
    ):
        assert message in ui
    assert "setRemoteClientsLoading(loading)" in ui
    assert "this._remoteClientsAvailable" in ui
    assert "this._remoteClientsLoaded" in ui
    assert "this._pairingStatusAvailable" in ui
    assert "claim status temporarily unavailable; retrying" in ui
    assert "this._pairingRetryAt" in applet
    assert "this._pairingRetryAttempt" in applet
    assert "Math.min(60, Math.pow(2" in applet
    assert "Device listing requires a newer Codex version" not in ui


def test_graph_renderer_has_separate_step_bar_and_reset_paths():
    source = GRAPH_SOURCE.read_text(encoding="utf-8")

    assert "function _drawQuotaSteps" in source
    assert "function _drawActivityBars" in source
    assert "function _drawQuotaArea" in source
    assert "function _drawQuotaEndpoint" in source
    assert "function _drawResetMarkers" in source
    assert "series.segments" in source
    assert "series.kind === 'activity'" in source
    assert "context.lineTo(x, previousY)" in source


def test_graph_supports_dynamic_left_and_right_axes():
    source = GRAPH_SOURCE.read_text(encoding="utf-8")

    assert "view._rightAxis" in source
    assert "function _updateAxis" in source
    assert "data.axes.left" in source
    assert "data.axes.right" in source


def test_graph_hover_uses_allocated_actor_width_outside_repaint():
    source = GRAPH_SOURCE.read_text(encoding="utf-8")
    motion_handler = source[
        source.index("view._area.connect('motion-event'") :
        source.index("view._area.connect('leave-event'")
    ]

    assert "view._area.width" in motion_handler
    assert "get_surface_size" not in motion_handler


def test_graph_marks_uncollected_history_and_explains_its_boundary():
    graph = GRAPH_SOURCE.read_text(encoding="utf-8")
    ui = UI_SOURCE.read_text(encoding="utf-8")

    assert "function _drawUncollectedHistory" in graph
    assert "area._collectionStart" in graph
    assert "No local history" in graph
    assert "History starts" in ui


def test_dashboard_sends_semantic_graph_payload():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "this._model.quotaSegments" in source
    assert "this._model.graphAxes" in source
    assert "mode," in source
    assert "rangeHours," in source
    assert "axes," in source


def test_session_dashboard_has_keyboard_filters_and_project_groups():
    source = UI_SOURCE.read_text(encoding="utf-8")

    for label in ("All", "Active", "Attention", "Recent"):
        assert f"this._('{label}')" in source
    assert "this._model.sessionView" in source
    assert "codex-monitor-session-project" in source
    assert "add_style_pseudo_class('checked')" in source


def test_pairing_qr_uses_only_bounded_native_svg_rendering():
    applet = APPLET_SOURCE.read_text(encoding="utf-8")
    ui = UI_SOURCE.read_text(encoding="utf-8")

    assert "Modules.qr" not in applet
    assert "options.qr" not in ui
    assert "Gio.BytesIcon.new" in ui
    assert "ByteArray.fromString" in ui
    assert "function _validatedQrSvg" in ui
    assert "this._pairing.qrSvg" in ui
    assert "qrMatrix" not in applet + ui
    assert not APPLET_SOURCE.with_name("qr.js").exists()


def test_claimed_and_expired_pairings_clear_secrets_from_ui_memory():
    applet = APPLET_SOURCE.read_text(encoding="utf-8")
    ui = UI_SOURCE.read_text(encoding="utf-8")

    assert "this._pairing = null;" in applet
    assert "this._pairing = { claimed: true };" in ui
    assert "QR unavailable; use the manual code" in ui


def test_update_check_starts_only_after_snapshot_and_repeats_every_twelve_hours():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    snapshot_callback = source.index("this._snapshot = snapshot;")
    update_read = source.index("this._readUpdateStatus();")
    assert update_read > snapshot_callback
    assert "12 * 3600" in source
    assert "update_status" in source
    assert "update_check" in source
    assert "status === 'checking' || status === 'updating'" in source


def test_update_ui_is_conditional_confirmed_and_has_no_panel_badge():
    applet = APPLET_SOURCE.read_text(encoding="utf-8")
    ui = UI_SOURCE.read_text(encoding="utf-8")

    assert "Update Codex…" in ui
    assert "Updating Codex…" in ui
    assert "New Codex launches use this version" in ui
    assert "this._updateButton.visible = state.updateAvailable" in ui
    assert "onUpdate: this._confirmUpdate.bind(this)" in applet
    assert "update_start" in applet
    assert "confirmed: true" in applet
    assert "ModalDialog.ConfirmDialog" in applet
    assert "updateBadge" not in applet + ui


def test_bridge_queues_async_writes_and_closes_without_sync_io():
    source = APPLET_SOURCE.with_name("bridgeClient.js").read_text(encoding="utf-8")

    assert "ByteArray.fromString" in source
    assert "GLib.Bytes.new" in source
    assert "write_bytes_async" in source
    assert "write_bytes_finish" in source
    assert "close_async" in source
    assert "close_finish" in source
    assert "state.queue.push" in source
    assert "state.writing" in source
    assert "state.current = item" in source
    assert "state.current = null" in source
    assert "state.currentChunk" in source
    assert "write_all_async" not in source
    assert ".put_string(" not in source
    assert ".close(null)" not in source


def test_applet_uses_cinnamons_reloadable_commonjs_module_loader():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    for module in ("bridgeClient", "graph", "model", "ui"):
        assert f"require('./{module}')" in source
    assert "imports.applets[UUID]" not in source
