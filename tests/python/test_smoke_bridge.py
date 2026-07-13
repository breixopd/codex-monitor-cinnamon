import io
import json

import pytest

from scripts.smoke_bridge import run_probe


class FakeSession:
    def __init__(self, *, fail_clients=False):
        self.actions = []
        self.fail_clients = fail_clients

    def request(self, action, params=None):
        self.actions.append((action, params or {}))
        responses = {
            "snapshot": {"capturedAt": 10, "windows": {}},
            "sessions": {"active": [{"id": "active"}], "recent": [{"id": "recent"}]},
            "remote_status": {"status": "disabled"},
            "remote_start": {"status": "connected"},
            "remote_pair_start": {
                "pairingCode": "opaque-private-code",
                "manualPairingCode": "PRIVATE-MANUAL",
                "environmentId": "environment-1",
                "expiresAt": 1_900_000_000,
            },
            "remote_pair_status": {"claimed": False},
            "remote_clients": {"clients": [{"clientId": "client-1"}]},
            "remote_stop": {"status": "disabled"},
        }
        if action == "remote_clients" and self.fail_clients:
            raise RuntimeError("client list failed")
        return responses[action]


def test_run_probe_exercises_lifecycle_redacts_codes_and_restores_disabled_state():
    session = FakeSession()
    output = io.StringIO()

    result = run_probe(session, output=output, sleeper=lambda _seconds: None)

    assert result["snapshot"] is True
    assert result["sessionCount"] == 2
    assert result["remoteLifecycle"] is True
    assert result["pairClaimed"] is False
    assert result["clientCount"] == 1
    assert session.actions[-1] == ("remote_stop", {})
    rendered = output.getvalue()
    assert json.loads(rendered) == result
    assert "opaque-private-code" not in rendered
    assert "PRIVATE-MANUAL" not in rendered


def test_run_probe_restores_remote_state_when_lifecycle_step_fails():
    session = FakeSession(fail_clients=True)

    with pytest.raises(RuntimeError, match="client list failed"):
        run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    assert session.actions[-1] == ("remote_stop", {})
