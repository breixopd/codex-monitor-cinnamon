import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile

import pytest

from scripts import package_spice


ROOT = Path(__file__).resolve().parents[2]
UUID = "codex-monitor@breixopd"
VERSION = "1.2.3"


def _po_msgids(content):
    msgids = set()
    parts = None
    for line in [*content.splitlines(), ""]:
        if line.startswith("msgid "):
            if parts:
                msgids.add("".join(parts))
            parts = [json.loads(line.removeprefix("msgid "))]
        elif parts is not None and line.startswith('"'):
            parts.append(json.loads(line))
        elif parts is not None:
            if parts:
                msgids.add("".join(parts))
            parts = None
    msgids.discard("")
    return msgids


def _ascii_gettext_text(content):
    return "".join(
        character if ord(character) < 128 else f"__U{ord(character):06X}__"
        for character in content
    )


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


def test_translation_template_covers_every_javascript_gettext_call(tmp_path):
    runtime = ROOT / "files" / UUID
    sources = []
    for source in sorted(runtime.glob("*.js")):
        escaped = _ascii_gettext_text(source.read_text(encoding="utf-8"))
        destination = tmp_path / source.name
        destination.write_text(escaped, encoding="ascii")
        sources.append(destination)
    completed = subprocess.run(
        [
            "xgettext",
            "--language=JavaScript",
            "--from-code=UTF-8",
            "--keyword=_",
            "--keyword=this._",
            "--omit-header",
            "--no-location",
            "--sort-output",
            "--output=-",
            *(str(source) for source in sources),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    extracted = _po_msgids(completed.stdout)
    shipped = {
        _ascii_gettext_text(msgid)
        for msgid in _po_msgids(
            (runtime / "po" / f"{UUID}.pot").read_text(encoding="utf-8")
        )
    }

    assert extracted <= shipped, f"POT is missing msgids: {sorted(extracted - shipped)}"


def test_spices_builder_outputs_only_the_official_submission_layout(tmp_path):
    destination = package_spice.build_spice(tmp_path)

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


@pytest.mark.parametrize(
    ("relative_path", "kind", "message"),
    [
        (Path(".env"), "file", "hidden source entry"),
        (Path("applet.js~"), "file", "unknown runtime source entry"),
        (Path("linked-applet.js"), "symlink", "source symlink"),
    ],
)
def test_release_builder_rejects_stray_secrets_backups_and_symlinks(
    tmp_path, monkeypatch, relative_path, kind, message
):
    source_root = tmp_path / "source"
    applet = source_root / "files" / UUID
    store = source_root / "store"
    shutil.copytree(ROOT / "files" / UUID, applet)
    shutil.copytree(ROOT / "store", store)
    candidate = applet / relative_path
    if kind == "symlink":
        candidate.symlink_to(applet / "applet.js")
    else:
        candidate.write_text("private", encoding="utf-8")
    monkeypatch.setattr(package_spice, "APPLET", applet)
    monkeypatch.setattr(package_spice, "STORE", store)

    with pytest.raises(ValueError, match=message):
        package_spice.build_archives(tmp_path / "dist")


def test_runtime_and_spices_archives_are_allowlisted_and_reproducible(tmp_path):
    first_runtime, first_spice = package_spice.build_archives(tmp_path / "first")
    second_runtime, second_spice = package_spice.build_archives(tmp_path / "second")

    assert hashlib.sha256(first_runtime.read_bytes()).digest() == hashlib.sha256(
        second_runtime.read_bytes()
    ).digest()
    assert hashlib.sha256(first_spice.read_bytes()).digest() == hashlib.sha256(
        second_spice.read_bytes()
    ).digest()
    with zipfile.ZipFile(first_runtime) as archive:
        assert archive.namelist() == [
            f"{UUID}/{name}" for name in package_spice.RUNTIME_FILES
        ]
    with zipfile.ZipFile(first_spice) as archive:
        assert archive.namelist() == [
            *(f"{UUID}/{name}" for name in package_spice.STORE_FILES),
            *(
                f"{UUID}/files/{UUID}/{name}"
                for name in package_spice.RUNTIME_FILES
            ),
        ]


def test_release_shell_delegates_both_archives_to_the_manifest_builder():
    script = (ROOT / "scripts" / "package.sh").read_text(encoding="utf-8")

    assert 'python3 "$ROOT/scripts/package_spice.py" --archive-output "$ROOT/dist"' in script
    assert "\nzip -" not in script


def test_ci_runs_the_official_validator_with_its_pillow_environment():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    commands = {line.strip() for line in workflow.splitlines()}

    assert "sudo apt-get install --yes --no-install-recommends gettext" in commands
    assert "python ./validate-spice codex-monitor@breixopd" in commands
    assert "./validate-spice codex-monitor@breixopd" not in commands


def test_ci_pins_github_actions_and_python_tools_immutably():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert workflow.count(
        "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7"
    ) == 2
    assert (
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6"
        in workflow
    )
    assert (
        "actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38 # v6"
        in workflow
    )
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7"
        in workflow
    )
    assert "python -m pip install pytest==9.1.1 pillow==12.3.0 ruff==0.15.22" in workflow
    assert "branches: [main, dev]" in workflow


def test_store_screenshot_is_a_landscape_dashboard_compact_and_panel_composite():
    screenshot = ROOT / "store" / "screenshot.png"
    width, height = _png_size(screenshot)
    package = json.loads((ROOT / "package.json").read_text())

    assert 1100 <= width <= 1500
    assert 760 <= height <= 1100
    assert package["scripts"]["screenshot"] == "sh scripts/capture-store-screenshot.sh"
