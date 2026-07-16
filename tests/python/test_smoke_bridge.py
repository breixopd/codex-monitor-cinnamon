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
        client_failures=0,
        initial_status="disabled",
    ):
        self.actions = []
        self.fail_clients = fail_clients
        self.client_failures = client_failures
        self.initial_status = initial_status

    def request(self, action, params=None):
        self.actions.append((action, params or {}))
        responses = {
            "snapshot": {"capturedAt": 10, "windows": {}},
            "sessions": {"active": [{"id": "active"}], "recent": [{"id": "recent"}]},
            "remote_status": {
                "status": self.initial_status,
                "environmentId": "environment-1",
            },
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
        if action == "remote_clients" and self.client_failures > 0:
            self.client_failures -= 1
            raise RuntimeError("control channel is reconnecting")
        return responses[action]


def test_run_probe_reads_connected_remote_without_mutating_it():
    session = FakeSession(initial_status="connected")
    output = io.StringIO()

    result = run_probe(session, output=output, sleeper=lambda _seconds: None)

    assert result["snapshot"] is True
    assert result["sessionCount"] == 2
    assert result["remoteConnected"] is True
    assert result["clientCount"] == 1
    assert result["clientListSupported"] is True
    assert result["updateContract"] is True
    assert session.actions == [
        ("snapshot", {}),
        ("sessions", {"limit": 12}),
        ("update_status", {}),
        ("update_check", {"force": False}),
        ("remote_status", {}),
        ("remote_clients", {"environmentId": "environment-1"}),
    ]
    rendered = output.getvalue()
    assert json.loads(rendered) == result
    assert "client-1" not in rendered
    assert "environment-1" not in rendered


def test_run_probe_never_mutates_remote_when_read_only_step_fails():
    session = FakeSession(fail_clients=True, initial_status="connected")

    with pytest.raises(RuntimeError, match="client list failed"):
        run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    assert all(
        action not in {
            "remote_start",
            "remote_stop",
            "remote_pair_start",
            "remote_pair_status",
            "remote_revoke",
        }
        for action, _params in session.actions
    )


@pytest.mark.parametrize("initial_status", ["disabled", "connecting", "running"])
def test_run_probe_reports_unconnected_remote_without_starting_it(initial_status):
    session = FakeSession(initial_status=initial_status)

    result = run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    assert result["remoteConnected"] is False
    assert result["clientCount"] is None
    assert result["clientListSupported"] is None
    assert [action for action, _params in session.actions if action.startswith("remote_")] == [
        "remote_status"
    ]


def test_run_probe_can_skip_socket_operations_in_a_restricted_shell():
    session = FakeSession(fail_clients=True)

    result = run_probe(
        session,
        output=io.StringIO(),
        sleeper=lambda _seconds: None,
        check_remote=False,
    )

    assert result["snapshot"] is True
    assert result["remoteConnected"] is None
    assert result["clientListSupported"] is None
    assert all(
        not action.startswith("remote_") for action, _params in session.actions
    )


def test_live_smoke_preserves_remote_and_runs_full_visual_matrix():
    script = Path("scripts/smoke-live.sh").read_text(encoding="utf-8")
    matrix = Path("scripts/live-matrix.js").read_text(encoding="utf-8")
    remote_probe = Path("scripts/live-remote-probe.js").read_text(encoding="utf-8")

    assert "remote_stop" not in script
    assert 'x._remoteAction("remote_start"' not in script
    assert "delete imports.applets" not in script
    assert script.index('python3 "$ROOT/scripts/smoke_bridge.py"') < script.index(
        "dashboardCaptureReady"
    )
    assert '"--skip-remote"' in script
    assert "_codexMonitorDeviceProbe" in script
    assert "remoteDeviceBridge" in script
    assert "live-remote-probe.js" in script
    assert "clientCount" in remote_probe
    assert "clientId" not in remote_probe
    assert "displayName" not in remote_probe
    for mutable_action in (
        "remote_start",
        "remote_stop",
        "remote_pair_start",
        "remote_pair_status",
        "remote_revoke",
        "remote_repair",
    ):
        assert mutable_action not in remote_probe
    assert "remoteStatePreserved" in script
    assert "lifecycleRemovalClean" in script
    assert "lifecycleRestartClean" in script
    assert "dashboardCaptureReady" in script
    assert "org.Cinnamon.Screenshot" not in script
    assert "SCREENSHOT_DIR" not in script
    assert "json_true()" in script
    assert "wait_for_screenshot()" not in script
    assert "grep -F" in script
    assert ".*true" not in script
    assert "_codexMonitorSmokeErrorIndex" in script
    assert "lookingGlassClean" in script
    assert "_dashboardScroll.vscroll.adjustment.set_value(0)" in script
    assert "imports.ui.main.loadTheme()" in script
    assert 'themeManager.emit("theme-set")' in script
    assert "get_padding(imports.gi.St.Side.TOP)===8" in script
    assert "menuItemVerticalPadding" in script
    assert "dashboardTextCurrent" in script
    assert "outerTopInset" in script
    assert "outerBottomInset" in script
    assert "hoverLeftReady" in script
    assert "sleep 0.2" not in script
    assert "footerCompactFits" in script
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
        "remoteRepair",
        "remoteDevicesLoading",
        "remoteDevicesUnavailable",
        "remoteDevicesUnsupported",
        "remoteDevicesEmpty",
        "remoteDevicesListed",
        "qrScrollOverflow",
        "qrFallback",
        "pairingClaimed",
        "updateCurrent",
        "footerVersionCurrent",
        "footerUsageCurrent",
        "updateAvailable",
        "updateUpdating",
        "updateFailed",
        "sessionsEmpty",
        "sessionsAttentionFilter",
        "sessionsUnavailable",
    ):
        assert state in matrix


def test_run_probe_retries_client_list_during_channel_readiness_race():
    session = FakeSession(client_failures=2, initial_status="connected")

    result = run_probe(session, output=io.StringIO(), sleeper=lambda _seconds: None)

    client_calls = [
        action for action, _params in session.actions if action == "remote_clients"
    ]
    assert len(client_calls) == 3
    assert result["remoteConnected"] is True


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
