import io
import json
import subprocess

from codex_bridge.rpc import AppServerClient, RpcError


class FakeProcess:
    def __init__(self, responses):
        self.stdin = io.StringIO()
        self.stdout = iter(json.dumps(item) + "\n" for item in responses)
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_client_initializes_and_retains_notifications_while_waiting_for_response():
    update = {"rateLimits": {"primary": {"usedPercent": 37}}}
    process = FakeProcess(
        [
            {"method": "account/rateLimits/updated", "params": update},
            {"id": 1, "result": {"userAgent": "codex"}},
            {"id": 2, "result": {"rateLimits": {"primary": None}}},
        ]
    )
    client = AppServerClient(process=process, timeout_seconds=0.5)

    client.initialize()
    result = client.request("account/rateLimits/read")

    sent = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert sent[0] == {
        "id": 1,
        "method": "initialize",
        "params": {
            "clientInfo": {
                "name": "codex-monitor-cinnamon",
                "title": "Codex Monitor",
                "version": "1.0.0",
            },
            "capabilities": {
                "experimentalApi": True,
                "requestAttestation": False,
            },
        },
    }
    assert sent[1] == {"method": "initialized"}
    assert sent[2] == {"id": 2, "method": "account/rateLimits/read"}
    assert result == {"rateLimits": {"primary": None}}
    assert client.wait_for_notification(
        "account/rateLimits/updated", timeout_seconds=0
    ) == update
    assert client.wait_for_notification(
        "account/rateLimits/updated", timeout_seconds=0
    ) is None


def test_client_raises_sanitized_error_for_rpc_failure():
    process = FakeProcess(
        [
            {"id": 1, "result": {}},
            {"id": 2, "error": {"code": -32000, "message": "token expired"}},
        ]
    )
    client = AppServerClient(process=process, timeout_seconds=0.5)
    client.initialize()

    try:
        client.request("account/rateLimits/read")
    except RpcError as error:
        assert str(error) == "Codex request failed (-32000)"
        assert error.code == -32000
    else:
        raise AssertionError("expected a sanitized RPC error")


def test_close_kills_app_server_that_ignores_termination():
    class StubbornProcess(FakeProcess):
        def __init__(self):
            super().__init__([])
            self.terminated = False
            self.killed = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("codex app-server", timeout)
            return -9

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = StubbornProcess()
    client = AppServerClient(process=process, timeout_seconds=0.01)

    client.close()

    assert process.terminated is True
    assert process.killed is True
