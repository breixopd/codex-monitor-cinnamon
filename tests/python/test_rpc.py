import io
import json

from codex_bridge.rpc import AppServerClient


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


def test_client_initializes_and_skips_notifications_while_waiting_for_response():
    process = FakeProcess(
        [
            {"method": "account/rateLimits/updated", "params": {}},
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
                "version": "0.1.0",
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
    except RuntimeError as error:
        assert str(error) == "Codex request failed (-32000)"
    else:
        raise AssertionError("expected a sanitized RPC error")
