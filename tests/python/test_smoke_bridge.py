import io
import json
from pathlib import Path

import pytest

from scripts.smoke_bridge import run_probe


class FakeSession:
    def __init__(
        self, *, fail_clients=False, pair_status_failures=0, initial_status="disabled"
    ):
        self.actions = []
        self.fail_clients = fail_clients
        self.pair_status_failures = pair_status_failures
        self.initial_status = initial_status

    def request(self, action, params=None):
        self.actions.append((action, params or {}))
        responses = {
            "snapshot": {"capturedAt": 10, "windows": {}},
            "sessions": {"active": [{"id": "active"}], "recent": [{"id": "recent"}]},
            "remote_status": {"status": self.initial_status},
            "remote_start": {"status": "connected"},
            "remote_pair_start": {
                "pairingCode": "opaque-private-code",
                "manualPairingCode": "PRIVATE-MANUAL",
                "environmentId": "environment-1",
                "expiresAt": 1_900_000_000,
            },
            "remote_pair_status": {"claimed": False},
            "remote_clients": {"clients": [{"clientId": "client-1"}]},
        }
        if action == "remote_clients" and self.fail_clients:
            raise RuntimeError("client list failed")
        if action == "remote_pair_status" and self.pair_status_failures > 0:
            self.pair_status_failures -= 1
            raise RuntimeError("proxy is restarting")
        return responses[action]


def test_run_probe_exercises_lifecycle_redacts_codes_and_leaves_remote_running():
    session = FakeSession()
    output = io.StringIO()

    result = run_probe(session, output=output, sleeper=lambda _seconds: None)

    assert result["snapshot"] is True
    assert result["sessionCount"] == 2
    assert result["remoteLifecycle"] is True
    assert result["pairClaimed"] is False
    assert result["pairStatusSupported"] is True
    assert result["clientCount"] == 1
    assert result["clientListSupported"] is True
    assert result["remoteLeftRunning"] is True
    assert all(action != "remote_stop" for action, _params in session.actions)
    rendered = output.getvalue()
    assert json.loads(rendered) == result
    assert "opaque-private-code" not in rendered
    assert "PRIVATE-MANUAL" not in rendered


def test_run_probe_never_stops_live_remote_when_lifecycle_step_fails():
    session = FakeSession(fail_clients=True)

    with pytest.raises(RuntimeError, match="client list failed"):
        run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    assert all(action != "remote_stop" for action, _params in session.actions)


def test_live_smoke_connects_remote_before_capturing_dashboard():
    script = Path("scripts/smoke-live.sh").read_text(encoding="utf-8")

    assert "remote_stop" not in script
    assert 'x._remoteAction("remote_start",{confirmed:true})' in script
    assert script.index('python3 "$ROOT/scripts/smoke_bridge.py"') < script.index(
        '"$SCREENSHOT_DIR/dashboard.png"'
    )
    assert "settledRemote" in script


def test_run_probe_retries_pair_status_during_proxy_readiness_race():
    session = FakeSession(pair_status_failures=2)

    result = run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    pair_status_calls = [
        action for action, _params in session.actions if action == "remote_pair_status"
    ]
    assert len(pair_status_calls) == 3
    assert result["remoteLeftRunning"] is True


def test_run_probe_completes_start_from_connecting_socket_fallback():
    session = FakeSession(initial_status="connecting")

    result = run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    assert ("remote_start", {"confirmed": True}) in session.actions
    assert result["remoteLifecycle"] is True
