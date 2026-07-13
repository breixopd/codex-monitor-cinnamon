from pathlib import Path


APPLET_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "files"
    / "codex-monitor@breixopd"
    / "applet.js"
)
UI_SOURCE = APPLET_SOURCE.with_name("ui.js")
STYLESHEET_SOURCE = APPLET_SOURCE.with_name("stylesheet.css")
GRAPH_SOURCE = APPLET_SOURCE.with_name("graph.js")


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


def test_indicator_severities_have_distinct_semantic_styles():
    source = STYLESHEET_SOURCE.read_text(encoding="utf-8")

    assert ".codex-indicator-warning" in source
    assert ".codex-indicator-critical" in source
    assert ".codex-indicator-success" in source
    assert ".codex-indicator-info" in source
    assert "#e8a641" in source
    assert "#e05a62" in source


def test_graph_renderer_has_separate_step_bar_and_reset_paths():
    source = GRAPH_SOURCE.read_text(encoding="utf-8")

    assert "function _drawQuotaSteps" in source
    assert "function _drawActivityBars" in source
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


def test_dashboard_sends_semantic_graph_payload():
    source = UI_SOURCE.read_text(encoding="utf-8")

    assert "this._model.quotaSegments" in source
    assert "this._model.graphAxes" in source
    assert "mode," in source
    assert "rangeHours," in source
    assert "axes," in source


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
