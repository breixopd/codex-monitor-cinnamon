from pathlib import Path


APPLET_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "files"
    / "codex-monitor@breixopd"
    / "applet.js"
)
UI_SOURCE = APPLET_SOURCE.with_name("ui.js")
STYLESHEET_SOURCE = APPLET_SOURCE.with_name("stylesheet.css")


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
