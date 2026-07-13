#!/usr/bin/env python3
"""Exercise the installed Codex Monitor bridge without printing sensitive data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time


class BridgeSession:
    def __init__(self, helper, codex, *, codex_home=None, timeout=25):
        self.timeout = timeout
        self._next_id = 1
        self._data_dir = tempfile.TemporaryDirectory(prefix="codex-monitor-smoke-")
        command = [
            sys.executable,
            str(helper),
            "--codex",
            codex,
            "--data-dir",
            self._data_dir.name,
            "--history-days",
            "7",
        ]
        if codex_home:
            command.extend(["--codex-home", codex_home])
        self.process = subprocess.Popen(
            command,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            close_fds=True,
        )

    def request(self, action, params=None):
        request_id = f"smoke-{self._next_id}"
        self._next_id += 1
        message = {"id": request_id, "action": action, "params": params or {}}
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        readable, _, _ = select.select([self.process.stdout], [], [], self.timeout)
        if not readable:
            raise TimeoutError("Codex Monitor bridge smoke request timed out")
        raw = self.process.stdout.readline()
        if not raw:
            raise RuntimeError("Codex Monitor bridge exited during smoke test")
        try:
            response = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError("Codex Monitor bridge returned invalid JSON") from None
        if response.get("id") != request_id:
            raise RuntimeError("Codex Monitor bridge returned an uncorrelated response")
        if response.get("ok") is not True:
            error = response.get("error") or {}
            code = error.get("code") if isinstance(error, dict) else "unknown"
            raise RuntimeError(f"Codex Monitor bridge action failed ({code})")
        return response.get("data")

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self._data_dir.cleanup()


def _connected_status(session, initial, sleeper):
    if initial.get("status") == "connected":
        return initial
    status = session.request("remote_start", {"confirmed": True})
    for _attempt in range(10):
        if status.get("status") == "connected":
            return status
        sleeper(1)
        status = session.request("remote_status")
    raise RuntimeError("Remote Control did not connect during smoke test")


def _retry_remote_request(session, action, params, sleeper, *, attempts=10):
    for attempt in range(attempts):
        try:
            return session.request(action, params)
        except RuntimeError:
            if attempt + 1 == attempts:
                raise
            sleeper(1)
    raise RuntimeError("Remote Control request did not complete during smoke test")


def run_probe(session, *, output=sys.stdout, sleeper=time.sleep):
    """Run the live bridge contract and emit only non-sensitive assertions."""

    initial = session.request("remote_status")
    if initial.get("status") not in {"disabled", "connected"}:
        raise RuntimeError("Remote Control initial state was not smoke-testable")
    snapshot = session.request("snapshot")
    sessions = session.request("sessions", {"limit": 12})
    status = _connected_status(session, initial, sleeper)
    pairing = session.request("remote_pair_start")
    pairing_status = _retry_remote_request(
        session,
        "remote_pair_status",
        {
            "pairingCode": pairing.get("pairingCode"),
            "manualPairingCode": pairing.get("manualPairingCode"),
        },
        sleeper,
    )
    environment_id = pairing.get("environmentId") or status.get("environmentId")
    clients = _retry_remote_request(
        session,
        "remote_clients",
        {"environmentId": environment_id},
        sleeper,
    )
    result = {
        "snapshot": isinstance(snapshot, dict) and "capturedAt" in snapshot,
        "sessionCount": len(sessions.get("active") or [])
        + len(sessions.get("recent") or []),
        "remoteLifecycle": status.get("status") == "connected",
        "pairClaimed": bool(pairing_status.get("claimed")),
        "pairStatusSupported": pairing_status.get("supported") is not False,
        "clientCount": len(clients.get("clients") or []),
        "clientListSupported": clients.get("supported") is not False,
        # Stopping the live daemon also terminates the Codex session running this
        # smoke test. Stop behavior is covered by isolated command tests instead.
        "remoteLeftRunning": True,
    }
    output.write(json.dumps(result, sort_keys=True) + "\n")
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--codex-home")
    return parser.parse_args(argv)


def main(argv=None):
    options = parse_args(argv)
    session = BridgeSession(
        options.helper, options.codex, codex_home=options.codex_home
    )
    try:
        result = run_probe(session)
    finally:
        session.close()
    return 0 if result["snapshot"] and result["remoteLifecycle"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
