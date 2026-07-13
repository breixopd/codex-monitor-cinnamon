import json
import subprocess

from codex_bridge.remote import RemoteControl


class FakeStatusClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    def initialize(self):
        self.calls.append(("initialize", None))

    def request(self, method, params=None):
        self.calls.append((method, params))
        return self.response

    def close(self):
        self.closed = True


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


def test_remote_pair_parses_code_without_persisting_it():
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

    remote = RemoteControl("/usr/bin/codex", runner=runner)

    result = remote.pair()

    assert result == {
        "pairingCode": "opaque-code",
        "manualPairingCode": "ABCD-EFGH",
        "environmentId": "environment-1",
        "expiresAt": 1_800_000_000,
    }
    assert calls[0][0] == ["/usr/bin/codex", "remote-control", "pair", "--json"]
    assert calls[0][1]["shell"] is False


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
