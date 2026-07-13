import io
import json
from pathlib import Path

import pytest

from scripts.smoke_bridge import run_probe


class FakeSession:
    def __init__(
        self,
        *,
        fail_clients=False,
        pair_start_failures=0,
        pair_status_failures=0,
        initial_status="disabled",
    ):
        self.actions = []
        self.fail_clients = fail_clients
        self.pair_start_failures = pair_start_failures
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
                "qrSvg": '<svg viewBox="0 0 11 11"></svg>',
            },
            "remote_pair_status": {"claimed": False},
            "remote_clients": {"clients": [{"clientId": "client-1"}]},
            "update_status": {
                "installedVersion": "0.144.3",
                "latestVersion": "0.145.0",
                "updateAvailable": True,
                "checkedAt": 1_800_000_000,
                "status": "idle",
                "message": None,
            },
            "update_check": {
                "installedVersion": "0.144.3",
                "latestVersion": "0.145.0",
                "updateAvailable": True,
                "checkedAt": 1_800_000_000,
                "status": "idle",
                "message": None,
            },
        }
        if action == "remote_clients" and self.fail_clients:
            raise RuntimeError("client list failed")
        if action == "remote_pair_start" and self.pair_start_failures > 0:
            self.pair_start_failures -= 1
            raise RuntimeError("proxy is restarting")
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
    assert result["pairingQrSvg"] is True
    assert result["updateContract"] is True
    assert all(action != "remote_stop" for action, _params in session.actions)
    assert all(action != "update_start" for action, _params in session.actions)
    rendered = output.getvalue()
    assert json.loads(rendered) == result
    assert "opaque-private-code" not in rendered
    assert "PRIVATE-MANUAL" not in rendered


def test_run_probe_never_stops_live_remote_when_lifecycle_step_fails():
    session = FakeSession(fail_clients=True)

    with pytest.raises(RuntimeError, match="client list failed"):
        run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    assert all(action != "remote_stop" for action, _params in session.actions)


def test_live_smoke_preserves_remote_and_runs_full_visual_matrix():
    script = Path("scripts/smoke-live.sh").read_text(encoding="utf-8")
    matrix = Path("scripts/live-matrix.js").read_text(encoding="utf-8")

    assert "remote_stop" not in script
    assert 'x._remoteAction("remote_start"' not in script
    assert "delete imports.applets" not in script
    assert script.index('python3 "$ROOT/scripts/smoke_bridge.py"') < script.index(
        '"$SCREENSHOT_DIR/dashboard.png"'
    )
    assert "remoteStatePreserved" in script
    assert "lifecycleRemovalClean" in script
    assert "lifecycleRestartClean" in script
    assert "dashboardCaptureReady" in script
    assert 'rm -f -- "$SCREENSHOT_DIR/dashboard.png"' in script
    assert "json_true()" in script
    assert "wait_for_screenshot()" in script
    assert "grep -F" in script
    assert ".*true" not in script
    assert "_codexMonitorSmokeErrorIndex" in script
    assert "lookingGlassClean" in script
    for value in ('"quota"', '"activity"', '"both"', "24", "168", "720"):
        assert value in matrix
    for state in (
        "emptyGraph",
        "singleGraph",
        "gapGraph",
        "denseGraph",
        "quotaWarning",
        "quotaCritical",
        "resetCritical",
        "remoteConnecting",
        "remoteError",
        "qrFallback",
        "pairingClaimed",
        "updateCurrent",
        "updateAvailable",
        "updateUpdating",
        "updateFailed",
        "sessionsEmpty",
        "sessionsAttentionFilter",
        "sessionsUnavailable",
    ):
        assert state in matrix


def test_run_probe_retries_pair_status_during_proxy_readiness_race():
    session = FakeSession(pair_status_failures=2)

    result = run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    pair_status_calls = [
        action for action, _params in session.actions if action == "remote_pair_status"
    ]
    assert len(pair_status_calls) == 3
    assert result["remoteLeftRunning"] is True


def test_run_probe_retries_pair_start_during_proxy_readiness_race():
    session = FakeSession(pair_start_failures=2)

    result = run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    pair_start_calls = [
        action for action, _params in session.actions if action == "remote_pair_start"
    ]
    assert len(pair_start_calls) == 3
    assert result["remoteLeftRunning"] is True


@pytest.mark.parametrize("initial_status", ["connecting", "running"])
def test_run_probe_completes_start_from_unconfirmed_running_state(initial_status):
    session = FakeSession(initial_status=initial_status)

    result = run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    assert ("remote_start", {"confirmed": True}) in session.actions
    assert result["remoteLifecycle"] is True


def test_dashboard_uses_only_cinnamons_native_context_settings_action():
    applet = Path("files/codex-monitor@breixopd/applet.js").read_text(
        encoding="utf-8"
    )
    dashboard = Path("files/codex-monitor@breixopd/ui.js").read_text(
        encoding="utf-8"
    )

    assert "onSettings" not in applet
    assert "onSettings" not in dashboard
    assert "cinnamon-settings', 'applets'" not in applet


def test_quota_cards_do_not_repeat_panel_bars_in_the_dashboard():
    dashboard = Path("files/codex-monitor@breixopd/ui.js").read_text(
        encoding="utf-8"
    )

    assert "BarLevel" not in dashboard
    assert "codex-monitor-bar" not in dashboard
