import json
import subprocess

from codex_bridge.remote import RemoteControl
from codex_bridge.rpc import RpcError


class FakeStatusClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    def initialize(self):
        self.calls.append(("initialize", None))

    def request(self, method, params=None):
        self.calls.append((method, params))
        if isinstance(self.response, dict) and method in self.response:
            return self.response[method]
        return self.response

    def close(self):
        self.closed = True


class FailingInitializeClient(FakeStatusClient):
    def initialize(self):
        raise RuntimeError("proxy daemon is not running")


class FailingRequestClient(FakeStatusClient):
    def request(self, method, params=None):
        self.calls.append((method, params))
        raise RpcError(-32601)


class BrokenRequestClient(FakeStatusClient):
    def request(self, method, params=None):
        self.calls.append((method, params))
        raise RuntimeError("remote backend failed")


def test_remote_status_reads_running_daemon_through_proxy():
    client = FakeStatusClient(
        {
            "status": "connected",
            "serverName": "mint-workstation",
            "installationId": "install-1",
            "environmentId": "environment-1",
        }
    )
    remote = RemoteControl("/usr/bin/codex", client_factory=lambda: client)

    result = remote.status()

    assert result["status"] == "connected"
    assert result["serverName"] == "mint-workstation"
    assert client.calls == [
        ("initialize", None),
        ("remoteControl/status/read", None),
    ]
    assert client.closed is True


def test_remote_status_treats_unavailable_proxy_daemon_as_disabled():
    client = FailingInitializeClient({})
    remote = RemoteControl("codex", client_factory=lambda: client)

    assert remote.status() == {"status": "disabled"}
    assert client.closed is True


def test_remote_status_discards_invalid_or_oversized_metadata():
    client = FakeStatusClient(
        {
            "status": "connected",
            "serverName": {"secret": "do not stringify"},
            "installationId": "x" * 257,
            "environmentId": "environment-1",
        }
    )
    remote = RemoteControl("codex", client_factory=lambda: client)

    result = remote.status()

    assert result == {
        "status": "connected",
        "serverName": None,
        "installationId": None,
        "environmentId": "environment-1",
    }
    assert "secret" not in repr(result)


def test_remote_display_metadata_is_collapsed_to_single_line_text():
    client = FakeStatusClient(
        {
            "status": "connected",
            "serverName": "  Mint\n workstation\t ",
            "installationId": "install-1",
            "environmentId": "environment-1",
        }
    )
    remote = RemoteControl("codex", client_factory=lambda: client)

    assert remote.status()["serverName"] == "Mint workstation"


def test_remote_pair_start_uses_proxy_and_normalizes_code_without_persisting_it():
    client = FakeStatusClient(
        {
            "pairingCode": "opaque-code",
            "manualPairingCode": "ABCD-EFGH",
            "environmentId": "environment-1",
            "expiresAt": 1_800_000_000,
            "unexpectedSecret": "discard me",
        }
    )
    remote = RemoteControl("/usr/bin/codex", client_factory=lambda: client)

    result = remote.pair_start()

    assert result == {
        "pairingCode": "opaque-code",
        "manualPairingCode": "ABCD-EFGH",
        "environmentId": "environment-1",
        "expiresAt": 1_800_000_000,
    }
    assert "unexpectedSecret" not in repr(result)
    assert client.calls == [
        ("initialize", None),
        ("remoteControl/pairing/start", {"manualCode": True}),
    ]
    assert client.closed is True


def test_remote_pair_start_falls_back_to_fixed_cli_when_proxy_method_fails():
    client = FailingRequestClient({})
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "pairingCode": "opaque-code",
                    "manualPairingCode": "ABCD-EFGH",
                    "environmentId": "environment-1",
                    "expiresAt": 1_800_000_000,
                }
            ),
            stderr="",
        )

    remote = RemoteControl(
        "/usr/bin/codex", runner=runner, client_factory=lambda: client
    )

    assert remote.pair_start()["manualPairingCode"] == "ABCD-EFGH"
    assert calls[0][0] == ["/usr/bin/codex", "remote-control", "pair", "--json"]
    assert calls[0][1]["shell"] is False
    assert client.closed is True


def test_remote_pair_start_does_not_mask_non_capability_proxy_errors():
    client = BrokenRequestClient({})
    remote = RemoteControl(
        "codex",
        runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("CLI fallback must not run")
        ),
        client_factory=lambda: client,
    )

    try:
        remote.pair_start()
    except RuntimeError as error:
        assert str(error) == "remote backend failed"
    else:
        raise AssertionError("expected backend failure")


def test_remote_pair_status_uses_in_memory_pairing_codes():
    client = FakeStatusClient({"claimed": True, "extra": "discard"})
    remote = RemoteControl("codex", client_factory=lambda: client)

    result = remote.pair_status("opaque-code", "ABCD-EFGH")

    assert result == {"claimed": True}
    assert client.calls[1] == (
        "remoteControl/pairing/status",
        {"pairingCode": "opaque-code"},
    )


def test_remote_pair_status_uses_manual_code_only_when_opaque_code_is_missing():
    client = FakeStatusClient({"claimed": False})
    remote = RemoteControl("codex", client_factory=lambda: client)

    assert remote.pair_status(None, "ABCD-EFGH") == {"claimed": False}
    assert client.calls[1] == (
        "remoteControl/pairing/status",
        {"manualPairingCode": "ABCD-EFGH"},
    )


def test_remote_pair_status_reports_unsupported_method_without_breaking_pairing():
    client = FailingRequestClient({})
    remote = RemoteControl("codex", client_factory=lambda: client)

    assert remote.pair_status("opaque-code") == {
        "claimed": False,
        "supported": False,
    }


def test_remote_clients_are_allowlisted_bounded_and_sorted_by_last_seen():
    client = FakeStatusClient(
        {
            "data": [
                {
                    "clientId": "client-old",
                    "displayName": "Tablet",
                    "deviceModel": "Mint Tab",
                    "deviceType": "tablet",
                    "platform": "android",
                    "osVersion": "16",
                    "appVersion": "1.2.2",
                    "lastSeenAt": 1_700_000_000,
                },
                {
                    "clientId": "client-new",
                    "displayName": "Phone",
                    "deviceType": "phone",
                    "platform": "android",
                    "appVersion": "1.2.3",
                    "lastSeenAt": 1_800_000_000,
                    "unexpectedSecret": "discard me",
                },
                {"clientId": ""},
            ]
        }
    )
    remote = RemoteControl("codex", client_factory=lambda: client)

    result = remote.clients("environment-1")

    assert [row["clientId"] for row in result["clients"]] == [
        "client-new",
        "client-old",
    ]
    assert result["clients"][0] == {
        "clientId": "client-new",
        "displayName": "Phone",
        "deviceModel": None,
        "deviceType": "phone",
        "platform": "android",
        "osVersion": None,
        "appVersion": "1.2.3",
        "lastSeenAt": 1_800_000_000,
    }
    assert "unexpectedSecret" not in repr(result)
    assert client.calls[1] == (
        "remoteControl/client/list",
        {"environmentId": "environment-1", "limit": 50, "order": "desc"},
    )


def test_remote_client_display_fields_are_single_line_text():
    client = FakeStatusClient(
        {
            "data": [
                {
                    "clientId": "client-1",
                    "displayName": "  Personal\n phone ",
                    "platform": " android\t16 ",
                }
            ]
        }
    )
    remote = RemoteControl("codex", client_factory=lambda: client)

    result = remote.clients("environment-1")

    assert result["clients"][0]["displayName"] == "Personal phone"
    assert result["clients"][0]["platform"] == "android 16"


def test_remote_clients_reports_unsupported_method_without_breaking_remote_status():
    client = FailingRequestClient({})
    remote = RemoteControl("codex", client_factory=lambda: client)

    assert remote.clients("environment-1") == {
        "clients": [],
        "supported": False,
    }


def test_remote_revoke_uses_fixed_proxy_method_and_returns_normalized_result():
    client = FakeStatusClient({})
    remote = RemoteControl("codex", client_factory=lambda: client)

    result = remote.revoke("environment-1", "client-1")

    assert result == {"revoked": True}
    assert client.calls[1] == (
        "remoteControl/client/revoke",
        {"environmentId": "environment-1", "clientId": "client-1"},
    )


def test_remote_proxy_operations_reject_invalid_response_shapes():
    cases = [
        ("pair_start", {"pairingCode": "missing required values"}),
        ("pair_status", {"claimed": "yes"}),
        ("clients", {"data": "not-a-list"}),
    ]

    for operation, response in cases:
        remote = RemoteControl("codex", client_factory=lambda r=response: FakeStatusClient(r))
        try:
            if operation == "pair_start":
                remote.pair_start()
            elif operation == "pair_status":
                remote.pair_status("opaque", None)
            else:
                remote.clients("environment-1")
        except RuntimeError as error:
            assert str(error) == "Codex remote-control response was invalid"
        else:
            raise AssertionError(f"expected invalid {operation} response")


def test_remote_start_and_stop_use_fixed_argument_lists():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout='{"status":"connected"}', stderr=""
        )

    remote = RemoteControl("codex", runner=runner)

    assert remote.start() == {"status": "connected"}
    assert remote.stop() == {"status": "disabled"}
    assert calls == [
        ["codex", "remote-control", "start", "--json"],
        ["codex", "remote-control", "stop", "--json"],
    ]


def test_remote_command_errors_do_not_expose_stderr():
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="private diagnostic contents"
        )

    remote = RemoteControl("codex", runner=runner)

    try:
        remote.start()
    except RuntimeError as error:
        assert str(error) == "Codex remote-control command failed"
    else:
        raise AssertionError("expected remote-control failure")


def test_remote_commands_receive_scoped_environment():
    captured = {}

    def runner(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            command, 0, stdout='{"status":"connected"}', stderr=""
        )

    remote = RemoteControl(
        "codex", runner=runner, environment={"CODEX_HOME": "/tmp/codex-home"}
    )

    remote.start()

    assert captured["env"] == {"CODEX_HOME": "/tmp/codex-home"}
