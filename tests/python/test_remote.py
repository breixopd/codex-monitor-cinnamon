import json
import shutil
import signal
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
        raise RuntimeError("control channel is not responding")


class FailingRequestClient(FakeStatusClient):
    def request(self, method, params=None):
        self.calls.append((method, params))
        raise RpcError(-32601)


class BrokenRequestClient(FakeStatusClient):
    def request(self, method, params=None):
        self.calls.append((method, params))
        raise RuntimeError("remote backend failed")


class FakeClock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def _write_proc_process(proc_root, pid, *, state, ppid, arguments, start_ticks):
    process = proc_root / str(pid)
    process.mkdir(parents=True)
    process.joinpath("cmdline").write_bytes(
        b"\0".join(str(argument).encode() for argument in arguments) + b"\0"
    )
    stat_fields = [state, str(ppid), *("0" for _ in range(17)), str(start_ticks)]
    process.joinpath("stat").write_text(
        f"{pid} (codex) {' '.join(stat_fields)}\n", encoding="utf-8"
    )
    return process


def test_remote_status_reads_running_daemon_through_control_channel():
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


def test_remote_status_treats_unavailable_control_channel_as_disabled():
    client = FailingInitializeClient({})
    remote = RemoteControl(
        "codex", client_factory=lambda: client, daemon_running=lambda: False
    )

    assert remote.status() == {"status": "disabled"}
    assert client.closed is True


def test_remote_status_probes_existing_daemon_when_control_channel_is_unavailable():
    client = FailingInitializeClient({})
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "connected",
                    "serverName": "mint-workstation",
                    "environmentId": "environment-1",
                    "daemon": {"status": "alreadyRunning"},
                }
            ),
            stderr="",
        )

    remote = RemoteControl(
        "codex",
        runner=runner,
        client_factory=lambda: client,
        daemon_running=lambda: True,
    )

    assert remote.status() == {
        "status": "connected",
        "serverName": "mint-workstation",
        "environmentId": "environment-1",
    }
    assert calls == [["codex", "remote-control", "start", "--json"]]


def test_remote_status_reports_running_when_existing_daemon_probe_fails():
    client = FailingRequestClient({})

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="private")

    remote = RemoteControl(
        "codex",
        runner=runner,
        client_factory=lambda: client,
        daemon_running=lambda: True,
    )

    assert remote.status() == {"status": "running"}


def test_remote_status_backs_off_unavailable_channel_without_blocking_every_poll():
    clock = FakeClock()
    clients = []

    def client_factory():
        client = FailingInitializeClient({})
        clients.append(client)
        return client

    remote = RemoteControl(
        "codex",
        client_factory=client_factory,
        daemon_running=lambda: True,
        clock=clock,
        runner=lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"connected","serverName":"mint-workstation"}',
            stderr="",
        ),
    )

    assert remote.status()["status"] == "connected"
    assert remote.status()["status"] == "connected"
    assert len(clients) == 1

    clock.advance(60)

    assert remote.status()["status"] == "connected"
    assert len(clients) == 2


def test_remote_status_retries_transient_existing_daemon_probe_failure():
    clock = FakeClock()
    probe_count = 0

    def runner(command, **kwargs):
        nonlocal probe_count
        probe_count += 1
        if probe_count == 1:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="private")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"connected","serverName":"mint-workstation"}',
            stderr="",
        )

    remote = RemoteControl(
        "codex",
        runner=runner,
        client_factory=lambda: FailingInitializeClient({}),
        daemon_running=lambda: True,
        clock=clock,
    )

    assert remote.status() == {"status": "running"}
    assert remote.status() == {"status": "running"}
    assert probe_count == 1

    clock.advance(60)

    assert remote.status()["status"] == "connected"
    assert probe_count == 2


def test_remote_status_invalidates_cached_connection_when_daemon_disappears():
    running = iter([True, False])
    client = FailingInitializeClient({})

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"connected","serverName":"mint-workstation"}',
            stderr="",
        )

    remote = RemoteControl(
        "codex",
        runner=runner,
        client_factory=lambda: client,
        daemon_running=lambda: next(running),
    )

    assert remote.status()["status"] == "connected"
    assert remote.status() == {"status": "disabled"}


def test_remote_process_detection_requires_same_user_remote_control_process(tmp_path):
    proc_root = tmp_path / "proc"
    remote_process = proc_root / "123"
    ordinary_process = proc_root / "456"
    remote_process.mkdir(parents=True)
    ordinary_process.mkdir()
    remote_process.joinpath("cmdline").write_bytes(
        b"/usr/bin/codex\0app-server\0--remote-control\0--listen\0unix://\0"
    )
    ordinary_process.joinpath("cmdline").write_bytes(
        b"/usr/bin/codex\0app-server\0daemon\0"
    )

    remote = RemoteControl("codex", proc_root=str(proc_root))

    assert remote._daemon_is_running() is True


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


def test_remote_pair_start_uses_control_channel_and_does_not_persist_code():
    client = FakeStatusClient(
        {
            "pairingCode": "opaque-code",
            "manualPairingCode": "ABCD-EFGH",
            "environmentId": "environment-1",
            "expiresAt": 1_800_000_000,
            "unexpectedSecret": "discard me",
        }
    )
    remote = RemoteControl(
        "/usr/bin/codex",
        client_factory=lambda: client,
        qr_encoder=lambda value: '<svg viewBox="0 0 11 11"></svg>',
    )

    result = remote.pair_start()

    assert result == {
        "pairingCode": "opaque-code",
        "manualPairingCode": "ABCD-EFGH",
        "environmentId": "environment-1",
        "expiresAt": 1_800_000_000,
        "qrSvg": '<svg viewBox="0 0 11 11"></svg>',
    }
    assert "unexpectedSecret" not in repr(result)
    assert client.calls == [
        ("initialize", None),
        ("remoteControl/pairing/start", {"manualCode": True}),
    ]
    assert client.closed is True


def test_remote_pair_start_falls_back_to_fixed_cli_when_channel_method_fails():
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


def test_remote_pair_start_does_not_mask_non_capability_channel_errors():
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


def test_remote_pair_status_distinguishes_unavailable_channel_from_unsupported_method():
    client = FailingInitializeClient({})
    remote = RemoteControl("codex", client_factory=lambda: client)

    assert remote.pair_status("opaque-code") == {
        "claimed": False,
        "available": False,
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


def test_remote_clients_distinguishes_unavailable_channel_from_unsupported_method():
    client = FailingInitializeClient({})
    remote = RemoteControl("codex", client_factory=lambda: client)

    assert remote.clients("environment-1") == {
        "clients": [],
        "available": False,
    }


def test_remote_revoke_uses_fixed_channel_method_and_returns_normalized_result():
    client = FakeStatusClient({})
    remote = RemoteControl("codex", client_factory=lambda: client)

    result = remote.revoke("environment-1", "client-1")

    assert result == {"revoked": True}
    assert client.calls[1] == (
        "remoteControl/client/revoke",
        {"environmentId": "environment-1", "clientId": "client-1"},
    )


def test_remote_channel_operations_reject_invalid_response_shapes():
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


def test_remote_start_caches_status_when_control_channel_is_temporarily_unavailable():
    client = FailingInitializeClient({})

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "connected",
                    "serverName": "mint-workstation",
                    "environmentId": "environment-1",
                }
            ),
            stderr="",
        )

    remote = RemoteControl(
        "codex",
        runner=runner,
        client_factory=lambda: client,
        daemon_running=lambda: True,
    )

    assert remote.start()["status"] == "connected"
    assert remote.status() == {
        "status": "connected",
        "serverName": "mint-workstation",
        "environmentId": "environment-1",
    }


def test_remote_start_cache_survives_unavailable_status_method():
    client = FailingRequestClient({})

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "connected",
                    "serverName": "mint-workstation",
                    "environmentId": "environment-1",
                }
            ),
            stderr="",
        )

    remote = RemoteControl(
        "codex",
        runner=runner,
        client_factory=lambda: client,
        daemon_running=lambda: True,
    )

    remote.start()

    assert remote.status()["status"] == "connected"


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


def test_remote_start_classifies_the_known_stuck_daemon_failure():
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=(
                "app server did not become ready on "
                "/home/user/.codex/app-server-control/app-server-control.sock\n"
                "private diagnostic details"
            ),
        )

    remote = RemoteControl("codex", runner=runner)

    try:
        remote.start()
    except RuntimeError as error:
        assert getattr(error, "code", None) == "REMOTE_DAEMON_STUCK"
        assert str(error) == "Codex Remote background service is stuck"
        assert "private" not in str(error)
    else:
        raise AssertionError("expected stuck daemon failure")


def test_remote_repair_terminates_only_the_validated_updater_then_bootstraps(tmp_path):
    codex_home = tmp_path / "codex-home"
    daemon_dir = codex_home / "app-server-daemon"
    release_dir = codex_home / "packages" / "standalone" / "releases" / "0.144.4"
    daemon_dir.mkdir(parents=True)
    release_dir.mkdir(parents=True)
    managed_codex = release_dir / "codex"
    managed_codex.write_text("managed codex", encoding="utf-8")
    managed_codex.chmod(0o700)
    daemon_dir.joinpath("app-server.pid").write_text(
        json.dumps({"pid": 200, "processStartTime": "earlier"}), encoding="utf-8"
    )
    daemon_dir.joinpath("app-server-updater.pid").write_text(
        json.dumps({"pid": 100, "processStartTime": "earlier"}), encoding="utf-8"
    )
    proc_root = tmp_path / "proc"
    app_process = _write_proc_process(
        proc_root,
        200,
        state="Z",
        ppid=100,
        arguments=[],
        start_ticks=2_000,
    )
    updater_process = _write_proc_process(
        proc_root,
        100,
        state="S",
        ppid=1,
        arguments=[managed_codex, "app-server", "daemon", "pid-update-loop"],
        start_ticks=1_000,
    )
    signals = []

    def pidfd_send_signal(pidfd, signum, _siginfo=None, _flags=0):
        signals.append((pidfd, signum))
        shutil.rmtree(app_process)
        shutil.rmtree(updater_process)

    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[1:4] == ["app-server", "daemon", "bootstrap"]:
            return subprocess.CompletedProcess(
                command, 0, stdout='{"status":"bootstrapped"}', stderr=""
            )
        return subprocess.CompletedProcess(
            command, 0, stdout='{"status":"connected"}', stderr=""
        )

    remote = RemoteControl(
        "/usr/bin/codex",
        runner=runner,
        environment={"CODEX_HOME": str(codex_home)},
        proc_root=str(proc_root),
    )

    assert hasattr(remote, "repair")
    remote.pidfd_open = lambda pid, _flags=0: pid
    remote.pidfd_send_signal = pidfd_send_signal
    remote.fd_close = lambda _fd: None

    assert remote.repair() == {"status": "connected"}
    assert signals == [(100, signal.SIGTERM)]
    assert calls == [
        [
            "/usr/bin/codex",
            "app-server",
            "daemon",
            "bootstrap",
            "--remote-control",
        ],
        ["/usr/bin/codex", "remote-control", "start", "--json"],
    ]


def test_remote_repair_refuses_if_the_updater_changes_after_pidfd_open(tmp_path):
    codex_home = tmp_path / "codex-home"
    daemon_dir = codex_home / "app-server-daemon"
    release_dir = codex_home / "packages" / "standalone" / "releases" / "0.144.4"
    daemon_dir.mkdir(parents=True)
    release_dir.mkdir(parents=True)
    managed_codex = release_dir / "codex"
    managed_codex.write_text("managed codex", encoding="utf-8")
    managed_codex.chmod(0o700)
    daemon_dir.joinpath("app-server.pid").write_text(
        json.dumps({"pid": 200, "processStartTime": "earlier"}), encoding="utf-8"
    )
    daemon_dir.joinpath("app-server-updater.pid").write_text(
        json.dumps({"pid": 100, "processStartTime": "earlier"}), encoding="utf-8"
    )
    proc_root = tmp_path / "proc"
    _write_proc_process(
        proc_root,
        200,
        state="Z",
        ppid=100,
        arguments=[],
        start_ticks=2_000,
    )
    updater_process = _write_proc_process(
        proc_root,
        100,
        state="S",
        ppid=1,
        arguments=[managed_codex, "app-server", "daemon", "pid-update-loop"],
        start_ticks=1_000,
    )
    signals = []

    def pidfd_open(pid, _flags=0):
        updater_process.joinpath("cmdline").write_bytes(
            b"/tmp/not-codex\0app-server\0daemon\0pid-update-loop\0"
        )
        return pid

    remote = RemoteControl(
        "/usr/bin/codex",
        runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, stdout='{"status":"connected"}', stderr=""
        ),
        environment={"CODEX_HOME": str(codex_home)},
        proc_root=str(proc_root),
    )
    remote.pidfd_open = pidfd_open
    remote.pidfd_send_signal = lambda *_args: signals.append(True)
    remote.fd_close = lambda _fd: None

    try:
        remote.repair()
    except RuntimeError:
        pass

    assert signals == []


def test_remote_repair_refuses_a_non_executable_updater_binary(tmp_path):
    codex_home = tmp_path / "codex-home"
    daemon_dir = codex_home / "app-server-daemon"
    release_dir = codex_home / "packages" / "standalone" / "releases" / "0.144.4"
    daemon_dir.mkdir(parents=True)
    release_dir.mkdir(parents=True)
    managed_codex = release_dir / "codex"
    managed_codex.write_text("not executable", encoding="utf-8")
    daemon_dir.joinpath("app-server.pid").write_text(
        json.dumps({"pid": 200, "processStartTime": "earlier"}), encoding="utf-8"
    )
    daemon_dir.joinpath("app-server-updater.pid").write_text(
        json.dumps({"pid": 100, "processStartTime": "earlier"}), encoding="utf-8"
    )
    proc_root = tmp_path / "proc"
    app_process = _write_proc_process(
        proc_root,
        200,
        state="Z",
        ppid=100,
        arguments=[],
        start_ticks=2_000,
    )
    updater_process = _write_proc_process(
        proc_root,
        100,
        state="S",
        ppid=1,
        arguments=[managed_codex, "app-server", "daemon", "pid-update-loop"],
        start_ticks=1_000,
    )
    signals = []

    def pidfd_send_signal(*_args):
        signals.append(True)
        shutil.rmtree(app_process)
        shutil.rmtree(updater_process)

    remote = RemoteControl(
        "/usr/bin/codex",
        runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, stdout='{"status":"connected"}', stderr=""
        ),
        environment={"CODEX_HOME": str(codex_home)},
        proc_root=str(proc_root),
    )
    remote.pidfd_open = lambda pid, _flags=0: pid
    remote.pidfd_send_signal = pidfd_send_signal
    remote.fd_close = lambda _fd: None

    try:
        remote.repair()
    except RuntimeError:
        pass

    assert signals == []


def test_remote_command_timeout_uses_sanitized_timeout_error():
    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr="private")

    remote = RemoteControl("codex", runner=runner)

    try:
        remote.start()
    except TimeoutError as error:
        assert str(error) == "Codex remote-control command timed out"
        assert "private" not in str(error)
    else:
        raise AssertionError("expected remote-control timeout")


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
