from pathlib import Path


def test_capture_uses_an_isolated_scene_and_never_captures_the_desktop():
    scene = Path("scripts/store-screenshot-scene.js").read_text(encoding="utf-8")
    capture = Path("scripts/capture-store-screenshot.sh").read_text(encoding="utf-8")

    assert "new Dashboard" in scene
    assert "new PopupMenu.PopupBaseMenuItem" in scene
    assert "style_class: 'codex-monitor-menu-item'" in scene
    assert "createFooterPreview" in scene
    assert "label('FOOTER')" in scene
    assert "dashboard._footer" in scene
    assert "Demo project" in scene
    assert "Example active session" in scene
    assert "Example phone" in scene
    assert "status: 'active'" in scene
    assert "status: 'notLoaded'" in scene
    assert "Main.uiGroup.add_child(root)" in scene
    assert "background-color: #14171a" in scene
    assert "global._codexMonitorDestroyScreenshotScene" in scene
    assert "x._snapshot" not in scene
    assert "x._sessions" not in scene
    assert "x._remoteStatus" not in scene
    assert "x._bridge" not in scene

    assert "store/screenshot.png" in capture
    assert "scripts/store-screenshot-scene.js" in capture
    assert "catch(error)" in capture
    assert "org.Cinnamon.ScreenshotArea" in capture
    assert "org.Cinnamon.Screenshot " not in capture
    assert "_codexMonitorDestroyScreenshotScene" in capture
    assert "scene-present" in capture
    assert "trap cleanup_store_capture" in capture
    assert '"instance-ready"' in capture
    assert '?"instance-ready":"loading"' in capture
    assert '[ "$attempt" -lt 60 ]' in capture
    assert "imports.ui.main.loadTheme()" in capture
    assert 'themeManager.emit("theme-set")' in capture


def test_capture_script_checks_the_isolated_scene_geometry():
    scene = Path("scripts/store-screenshot-scene.js").read_text(encoding="utf-8")
    capture = Path("scripts/capture-store-screenshot.sh").read_text(encoding="utf-8")

    assert "root.set_position(20, 20)" in scene
    assert "root.set_size(1300, 880)" in scene
    assert "x=20" in capture
    assert "y=20" in capture
    assert "width=1300" in capture
    assert "height=880" in capture
