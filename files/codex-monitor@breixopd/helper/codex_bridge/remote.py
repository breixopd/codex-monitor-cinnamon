"""Safe wrappers for Codex Remote Control."""

from __future__ import annotations

import json
import subprocess


class RemoteControl:
    def __init__(
        self, executable, *, runner=None, client_factory=None, environment=None
    ):
        self.executable = executable
        self.runner = runner or subprocess.run
        self.client_factory = client_factory
        self.environment = environment

    def status(self):
        if self.client_factory is None:
            return {"status": "disabled"}
        client = self.client_factory()
        try:
            client.initialize()
            value = client.request("remoteControl/status/read")
            return self._normalize_status(value)
        finally:
            client.close()

    def start(self):
        return self._run_json("start")

    def stop(self):
        self._run_json("stop")
        return {"status": "disabled"}

    def pair(self):
        value = self._run_json("pair")
        required = ("pairingCode", "environmentId", "expiresAt")
        if not all(key in value for key in required):
            raise RuntimeError("Codex remote-control response was invalid")
        return {
            "pairingCode": str(value["pairingCode"]),
            "manualPairingCode": (
                str(value["manualPairingCode"])
                if value.get("manualPairingCode") is not None
                else None
            ),
            "environmentId": str(value["environmentId"]),
            "expiresAt": int(value["expiresAt"]),
        }

    def _run_json(self, action):
        command = [self.executable, "remote-control", action, "--json"]
        completed = self.runner(
            command,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            env=self.environment,
        )
        if completed.returncode != 0:
            raise RuntimeError("Codex remote-control command failed")
        try:
            value = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError):
            raise RuntimeError("Codex remote-control response was invalid") from None
        if not isinstance(value, dict):
            raise RuntimeError("Codex remote-control response was invalid")
        return value

    @staticmethod
    def _normalize_status(value):
        if not isinstance(value, dict) or value.get("status") not in {
            "disabled",
            "connecting",
            "connected",
            "errored",
        }:
            raise RuntimeError("Codex remote-control status was invalid")
        return {
            "status": value["status"],
            "serverName": value.get("serverName"),
            "installationId": value.get("installationId"),
            "environmentId": value.get("environmentId"),
        }
