#!/usr/bin/env python3
"""Build the Cinnamon Spices submission tree from the canonical sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
UUID = "codex-monitor@breixopd"
APPLET = ROOT / "files" / UUID
STORE = ROOT / "store"
STORE_FILES = ("info.json", "README.md", "screenshot.png")


def _ignore_generated(_directory, names):
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validate_sources():
    missing = [name for name in STORE_FILES if not (STORE / name).is_file()]
    if missing:
        raise ValueError(f"missing Cinnamon Spices assets: {missing}")
    metadata = _read_json(APPLET / "metadata.json")
    info = _read_json(STORE / "info.json")
    if metadata.get("uuid") != UUID:
        raise ValueError("runtime UUID does not match the package directory")
    if metadata.get("author") != info.get("author"):
        raise ValueError("runtime and store authors do not match")
    forbidden = {"icon", "dangerous", "last-edited"}.intersection(metadata)
    if forbidden:
        raise ValueError(f"runtime metadata contains forbidden fields: {forbidden}")
    if info.get("license") != "MIT":
        raise ValueError("store metadata must declare the repository license")


def build_spice(output_root=None):
    """Return a fresh official-layout submission directory."""
    _validate_sources()
    output_root = Path(output_root or ROOT / "dist" / "spices")
    destination = output_root / UUID
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in STORE_FILES:
        shutil.copy2(STORE / name, destination / name)
    runtime_parent = destination / "files"
    runtime_parent.mkdir()
    shutil.copytree(
        APPLET,
        runtime_parent / UUID,
        ignore=_ignore_generated,
        symlinks=False,
    )
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "spices",
        help="parent directory for the generated UUID submission directory",
    )
    args = parser.parse_args()
    destination = build_spice(args.output)
    print(f"Built Cinnamon Spices package at {destination}")


if __name__ == "__main__":
    main()
