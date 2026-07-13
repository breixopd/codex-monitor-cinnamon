#!/usr/bin/env python3
"""Validate the source tree without importing Cinnamon-specific modules."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UUID = "codex-monitor@breixopd"
APPLET = ROOT / "files" / UUID
REQUIRED_FILES = {
    "applet.js",
    "bridgeClient.js",
    "graph.js",
    "helper/bridge.py",
    "metadata.json",
    "model.js",
    "settings-schema.json",
    "stylesheet.css",
    "ui.js",
}


def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_settings(schema):
    layout = schema.get("layout")
    if not isinstance(layout, dict) or layout.get("type") != "layout":
        raise ValueError("settings-schema.json must contain a layout")
    referenced = set()
    for value in layout.values():
        if isinstance(value, dict):
            referenced.update(value.get("keys", []))
    missing = sorted(key for key in referenced if key not in schema)
    if missing:
        raise ValueError(f"settings layout references missing keys: {missing}")


def validate_sources():
    missing = sorted(path for path in REQUIRED_FILES if not (APPLET / path).is_file())
    if missing:
        raise ValueError(f"missing applet files: {missing}")

    metadata = read_json(APPLET / "metadata.json")
    if metadata.get("uuid") != UUID:
        raise ValueError("metadata UUID does not match the package directory")
    supported = set(metadata.get("cinnamon-version", []))
    if not {"6.0", "6.2", "6.4", "6.6"}.issubset(supported):
        raise ValueError("metadata must cover Cinnamon 6.0 through 6.6")
    validate_settings(read_json(APPLET / "settings-schema.json"))

    applet_source = (APPLET / "applet.js").read_text(encoding="utf-8")
    ui_source = (APPLET / "ui.js").read_text(encoding="utf-8")
    if "Clutter.ActorAlign.CENTER" not in applet_source:
        raise ValueError("panel preview must declare centered actor alignment")
    if "codex-monitor-graph-legend" not in ui_source:
        raise ValueError("dashboard graph must expose a legend")
    if "Remote access · Experimental" in ui_source:
        raise ValueError("Remote Control must not use experimental dashboard copy")
    for text in ("Attention", "Recent", "Open Codex"):
        if text not in ui_source:
            raise ValueError(f"session dashboard is missing {text}")
    if "request('sessions'" not in applet_source:
        raise ValueError("applet must refresh Codex sessions")
    settings_source = (APPLET / "settings-schema.json").read_text(encoding="utf-8")
    if '"enable-remote"' in settings_source or '"remote-warning"' in settings_source:
        raise ValueError("Remote Control must not be hidden behind an experimental gate")
    for text in ("Pair device", "Paired devices", "Refresh devices"):
        if text not in ui_source:
            raise ValueError(f"Remote Control dashboard is missing {text}")
    for action in (
        "remote_pair_start",
        "remote_pair_status",
        "remote_clients",
        "remote_revoke",
    ):
        if action not in applet_source:
            raise ValueError(f"applet is missing Remote Control action {action}")

    for path in APPLET.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def main():
    validate_sources()
    print(f"Validated {UUID}")


if __name__ == "__main__":
    main()
