#!/usr/bin/env python3
"""Build allowlisted, reproducible runtime and Cinnamon Spices packages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
UUID = "codex-monitor@breixopd"
APPLET = ROOT / "files" / UUID
STORE = ROOT / "store"
STORE_FILES = ("README.md", "info.json", "screenshot.png")
RUNTIME_FILES = (
    "applet.js",
    "bridgeClient.js",
    "graph.js",
    "helper/bridge.py",
    "helper/codex_bridge/__init__.py",
    "helper/codex_bridge/active_processes.py",
    "helper/codex_bridge/history.py",
    "helper/codex_bridge/launcher.py",
    "helper/codex_bridge/models.py",
    "helper/codex_bridge/process.py",
    "helper/codex_bridge/protocol.py",
    "helper/codex_bridge/qr.py",
    "helper/codex_bridge/remote.py",
    "helper/codex_bridge/rpc.py",
    "helper/codex_bridge/service.py",
    "helper/codex_bridge/sessions.py",
    "helper/codex_bridge/updates.py",
    "helper/codex_bridge/websocket_rpc.py",
    "icon.png",
    "metadata.json",
    "model.js",
    f"po/{UUID}.pot",
    "settings-schema.json",
    "stylesheet.css",
    "ui.js",
)
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _allowed_directories(files):
    directories = set()
    for name in files:
        parent = Path(name).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _scan_allowlisted_tree(root, files, label):
    allowed_files = set(files)
    allowed_directories = _allowed_directories(files)
    found = set()

    def walk(directory, relative_directory=Path()):
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise ValueError(f"cannot inspect {label} sources") from error
        for entry in entries:
            relative = relative_directory / entry.name
            relative_name = relative.as_posix()
            if entry.name.startswith("."):
                raise ValueError(f"hidden source entry is forbidden: {relative_name}")
            if entry.is_symlink():
                raise ValueError(f"source symlink is forbidden: {relative_name}")
            if entry.is_dir(follow_symlinks=False):
                if relative_name not in allowed_directories and entry.name != "__pycache__":
                    raise ValueError(
                        f"unknown {label} source entry: {relative_name}"
                    )
                walk(Path(entry.path), relative)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise ValueError(f"unsupported source entry: {relative_name}")
            if "__pycache__" in relative.parts and relative.suffix in {".pyc", ".pyo"}:
                continue
            if relative_name not in allowed_files:
                raise ValueError(f"unknown {label} source entry: {relative_name}")
            found.add(relative_name)
    walk(root)
    missing = sorted(allowed_files - found)
    if missing:
        raise ValueError(f"missing {label} sources: {missing}")


def validate_package_sources():
    """Reject anything outside the explicit release manifests."""
    _scan_allowlisted_tree(APPLET, RUNTIME_FILES, "runtime")
    _scan_allowlisted_tree(STORE, STORE_FILES, "store")
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


def _copy_manifest(source, destination, files):
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)


def build_spice(output_root=None):
    """Return a fresh official-layout submission directory."""
    validate_package_sources()
    output_root = Path(output_root or ROOT / "dist" / "spices")
    destination = output_root / UUID
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    _copy_manifest(STORE, destination, STORE_FILES)
    _copy_manifest(APPLET, destination / "files" / UUID, RUNTIME_FILES)
    return destination


def _write_reproducible_zip(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for archive_name, source in entries:
                info = zipfile.ZipInfo(archive_name, date_time=_ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, source.read_bytes(), compresslevel=9)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def build_archives(output_root=None):
    """Build and return deterministic runtime and Spices ZIP paths."""
    output_root = Path(output_root or ROOT / "dist")
    destination = build_spice(output_root / "spices")
    runtime_archive = output_root / f"{UUID}.zip"
    spice_archive = output_root / f"{UUID}-spices.zip"
    _write_reproducible_zip(
        runtime_archive,
        ((f"{UUID}/{name}", APPLET / name) for name in RUNTIME_FILES),
    )
    _write_reproducible_zip(
        spice_archive,
        (
            *((f"{UUID}/{name}", destination / name) for name in STORE_FILES),
            *(
                (
                    f"{UUID}/files/{UUID}/{name}",
                    destination / "files" / UUID / name,
                )
                for name in RUNTIME_FILES
            ),
        ),
    )
    return runtime_archive, spice_archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "spices",
        help="parent directory for the generated UUID submission directory",
    )
    parser.add_argument(
        "--archive-output",
        type=Path,
        help="build both release ZIPs under this directory",
    )
    args = parser.parse_args()
    if args.archive_output is not None:
        runtime_archive, spice_archive = build_archives(args.archive_output)
        print(f"Built {runtime_archive}")
        print(f"Built {spice_archive}")
    else:
        destination = build_spice(args.output)
        print(f"Built Cinnamon Spices package at {destination}")


if __name__ == "__main__":
    main()
