"""Safe wrappers for Codex Remote Control."""

from __future__ import annotations

import json
import os
import stat
import subprocess

from .rpc import RpcError


class _ProxyUnavailable(RuntimeError):
    pass


class RemoteControl:
    def __init__(
        self,
        executable,
        *,
        runner=None,
        client_factory=None,
        environment=None,
        daemon_running=None,
    ):
        self.executable = executable
        self.runner = runner or subprocess.run
        self.client_factory = client_factory
        self.environment = environment
        self.daemon_running = daemon_running or self._control_socket_running
        self._last_status = None

    def status(self):
        if self.client_factory is None:
            return {"status": "disabled"}
        try:
            value = self._proxy_request("remoteControl/status/read")
        except _ProxyUnavailable:
            return self._fallback_status()
        except RpcError as error:
            if error.code != -32601:
                raise
            return self._fallback_status()
        self._last_status = self._normalize_status(value)
        return dict(self._last_status)

    def start(self):
        status = self._compact_status(self._normalize_status(self._run_json("start")))
        self._last_status = status
        return dict(status)

    def stop(self):
        self._run_json("stop")
        self._last_status = {"status": "disabled"}
        return dict(self._last_status)

    def pair_start(self):
        try:
            value = self._proxy_request(
                "remoteControl/pairing/start", {"manualCode": True}
            )
        except _ProxyUnavailable:
            # The pairing proxy method is newer than the Remote CLI surface and
            # is not available in every app-server build. The fixed CLI command
            # provides the same bounded JSON contract.
            value = self._run_json("pair")
        except RpcError as error:
            if error.code != -32601:
                raise
            value = self._run_json("pair")
        return self._normalize_pairing(value)

    @classmethod
    def _normalize_pairing(cls, value):
        if not isinstance(value, dict):
            raise RuntimeError("Codex remote-control response was invalid")
        pairing_code = cls._bounded_string(value.get("pairingCode"), maximum=4096)
        manual_code = cls._bounded_string(
            value.get("manualPairingCode"), maximum=256, optional=True
        )
        environment_id = cls._bounded_string(value.get("environmentId"))
        expires_at = value.get("expiresAt")
        if (
            pairing_code is None
            or environment_id is None
            or not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
        ):
            raise RuntimeError("Codex remote-control response was invalid")
        return {
            "pairingCode": pairing_code,
            "manualPairingCode": manual_code,
            "environmentId": environment_id,
            "expiresAt": expires_at,
        }

    def pair(self):
        """Compatibility alias for the original bridge action."""

        return self.pair_start()

    def pair_status(self, pairing_code, manual_pairing_code=None):
        pairing_code = self._bounded_string(
            pairing_code, maximum=4096, optional=True
        )
        manual_pairing_code = self._bounded_string(
            manual_pairing_code, maximum=256, optional=True
        )
        if pairing_code is None and manual_pairing_code is None:
            raise RuntimeError("Codex remote-control pairing code was invalid")
        params = (
            {"pairingCode": pairing_code}
            if pairing_code is not None
            else {"manualPairingCode": manual_pairing_code}
        )
        try:
            value = self._proxy_request("remoteControl/pairing/status", params)
        except _ProxyUnavailable:
            return {"claimed": False, "supported": False}
        except RpcError as error:
            if error.code != -32601:
                raise
            return {"claimed": False, "supported": False}
        if not isinstance(value, dict) or not isinstance(value.get("claimed"), bool):
            raise RuntimeError("Codex remote-control response was invalid")
        return {"claimed": value["claimed"]}

    def clients(self, environment_id):
        environment_id = self._require_identifier(environment_id, "environment")
        try:
            value = self._proxy_request(
                "remoteControl/client/list",
                {"environmentId": environment_id, "limit": 50, "order": "desc"},
            )
        except _ProxyUnavailable:
            return {"clients": [], "supported": False}
        except RpcError as error:
            if error.code != -32601:
                raise
            return {"clients": [], "supported": False}
        if not isinstance(value, dict) or not isinstance(value.get("data"), list):
            raise RuntimeError("Codex remote-control response was invalid")
        clients = []
        for raw in value["data"][:50]:
            client = self._normalize_client(raw)
            if client is not None:
                clients.append(client)
        clients.sort(key=lambda client: client["lastSeenAt"] or 0, reverse=True)
        return {"clients": clients}

    def revoke(self, environment_id, client_id):
        environment_id = self._require_identifier(environment_id, "environment")
        client_id = self._require_identifier(client_id, "client")
        value = self._proxy_request(
            "remoteControl/client/revoke",
            {"environmentId": environment_id, "clientId": client_id},
        )
        if not isinstance(value, dict):
            raise RuntimeError("Codex remote-control response was invalid")
        return {"revoked": True}

    def _proxy_request(self, method, params=None):
        if self.client_factory is None:
            raise RuntimeError("Codex remote control is unavailable")
        client = self.client_factory()
        try:
            try:
                client.initialize()
            except (OSError, RuntimeError, TimeoutError):
                raise _ProxyUnavailable("Codex remote-control proxy is unavailable") from None
            return client.request(method, params)
        finally:
            client.close()

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

    def _daemon_is_running(self):
        try:
            return bool(self.daemon_running())
        except (OSError, RuntimeError):
            return False

    def _fallback_status(self):
        if self._last_status is not None:
            return dict(self._last_status)
        return {
            "status": "connecting" if self._daemon_is_running() else "disabled"
        }

    def _control_socket_running(self):
        environment = self.environment or os.environ
        codex_home = environment.get("CODEX_HOME")
        if not codex_home:
            home = environment.get("HOME") or os.path.expanduser("~")
            codex_home = os.path.join(home, ".codex")
        socket_path = os.path.join(
            codex_home, "app-server-control", "app-server-control.sock"
        )
        return stat.S_ISSOCK(os.lstat(socket_path).st_mode)

    @staticmethod
    def _compact_status(value):
        return {key: item for key, item in value.items() if item is not None}

    @classmethod
    def _normalize_status(cls, value):
        if not isinstance(value, dict) or value.get("status") not in {
            "disabled",
            "connecting",
            "connected",
            "errored",
        }:
            raise RuntimeError("Codex remote-control status was invalid")
        return {
            "status": value["status"],
            "serverName": cls._display_string(value.get("serverName")),
            "installationId": cls._bounded_string(
                value.get("installationId"), optional=True
            ),
            "environmentId": cls._bounded_string(
                value.get("environmentId"), optional=True
            ),
        }

    @classmethod
    def _normalize_client(cls, value):
        if not isinstance(value, dict):
            return None
        client_id = cls._bounded_string(value.get("clientId"))
        if client_id is None:
            return None
        last_seen_at = value.get("lastSeenAt")
        if not isinstance(last_seen_at, int) or isinstance(last_seen_at, bool):
            last_seen_at = None
        return {
            "clientId": client_id,
            "displayName": cls._display_string(value.get("displayName")),
            "deviceModel": cls._display_string(value.get("deviceModel")),
            "deviceType": cls._display_string(value.get("deviceType")),
            "platform": cls._display_string(value.get("platform")),
            "osVersion": cls._display_string(value.get("osVersion")),
            "appVersion": cls._display_string(value.get("appVersion")),
            "lastSeenAt": last_seen_at,
        }

    @staticmethod
    def _bounded_string(value, *, maximum=256, optional=False):
        if value is None and optional:
            return None
        if not isinstance(value, str) or not value or len(value) > maximum:
            return None
        return value

    @staticmethod
    def _display_string(value, *, maximum=160):
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > maximum:
            return None
        return normalized

    @classmethod
    def _require_identifier(cls, value, name):
        normalized = cls._bounded_string(value)
        if normalized is None:
            raise RuntimeError(f"Codex remote-control {name} identifier was invalid")
        return normalized
