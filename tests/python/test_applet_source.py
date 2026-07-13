from pathlib import Path


APPLET_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "files"
    / "codex-monitor@breixopd"
    / "applet.js"
)


def test_refresh_keeps_status_badges_hidden_on_vertical_panels():
    source = APPLET_SOURCE.read_text(encoding="utf-8")

    for badge in ("_resetBadge", "_remoteBadge", "_staleBadge"):
        assert f"this.{badge}.visible = !vertical &&" in source
