import json
from pathlib import Path
import struct

from scripts.package_spice import build_spice


ROOT = Path(__file__).resolve().parents[2]
UUID = "codex-monitor@breixopd"
VERSION = "1.1.1"


def _png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_release_versions_and_store_metadata_are_consistent():
    runtime = json.loads((ROOT / "files" / UUID / "metadata.json").read_text())
    package = json.loads((ROOT / "package.json").read_text())
    info = json.loads((ROOT / "store" / "info.json").read_text())
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    rpc = (ROOT / "files" / UUID / "helper" / "codex_bridge" / "rpc.py").read_text()

    assert runtime["version"] == package["version"] == VERSION
    assert f'version = "{VERSION}"' in pyproject
    assert f'__version__ = "{VERSION}"' in (
        ROOT / "files" / UUID / "helper" / "codex_bridge" / "__init__.py"
    ).read_text()
    assert f"Project-Id-Version: {UUID} {VERSION}" in (
        ROOT / "files" / UUID / "po" / f"{UUID}.pot"
    ).read_text()
    assert "from . import __version__" in rpc
    assert runtime["uuid"] == UUID
    assert runtime["author"] == info["author"] == "breixopd"
    assert info["license"] == "MIT"
    assert "icon" not in runtime


def test_runtime_store_icon_is_a_nonempty_square_png():
    icon = ROOT / "files" / UUID / "icon.png"

    width, height = _png_size(icon)

    assert width == height
    assert width >= 64
    assert icon.stat().st_size > 500


def test_translation_template_is_source_only_and_covers_the_dashboard():
    runtime = ROOT / "files" / UUID
    template = runtime / "po" / f"{UUID}.pot"
    content = template.read_text(encoding="utf-8")

    assert content.count('\nmsgid "') >= 100
    assert 'msgid "Codex sessions"' in content
    assert 'msgid "Remote Control"' in content
    assert 'msgid "Update Codex…"' in content
    assert not any(runtime.rglob("*.mo"))


def test_spices_builder_outputs_only_the_official_submission_layout(tmp_path):
    destination = build_spice(tmp_path)

    assert destination == tmp_path / UUID
    assert sorted(path.name for path in destination.iterdir()) == [
        "README.md",
        "files",
        "info.json",
        "screenshot.png",
    ]
    runtime = destination / "files" / UUID
    assert (runtime / "applet.js").is_file()
    assert (runtime / "metadata.json").is_file()
    assert (runtime / "icon.png").is_file()
    assert (runtime / "po" / f"{UUID}.pot").is_file()
    assert not any(path.suffix in {".pyc", ".pyo"} for path in runtime.rglob("*"))
    assert not any(path.name == "__pycache__" for path in runtime.rglob("*"))


def test_ci_runs_the_official_validator_with_its_pillow_environment():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    commands = {line.strip() for line in workflow.splitlines()}

    assert "sudo apt-get install --yes --no-install-recommends gettext" in commands
    assert "python ./validate-spice codex-monitor@breixopd" in commands
    assert "./validate-spice codex-monitor@breixopd" not in commands


def test_ci_uses_current_node_24_github_action_majors():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert workflow.count("actions/checkout@v7") == 2
    assert "actions/setup-python@v6" in workflow
    assert "actions/setup-node@v6" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "branches: [main, dev]" in workflow


def test_store_screenshot_is_a_landscape_dashboard_compact_and_panel_composite():
    screenshot = ROOT / "store" / "screenshot.png"
    width, height = _png_size(screenshot)
    package = json.loads((ROOT / "package.json").read_text())

    assert 1100 <= width <= 1500
    assert 760 <= height <= 1100
    assert package["scripts"]["screenshot"] == "sh scripts/capture-store-screenshot.sh"
