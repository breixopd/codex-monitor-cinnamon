import json
import os
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from codex_bridge.updates import (
    MAX_CACHE_BYTES,
    UpdateManager,
    is_newer_version,
    parse_version,
)


NOW = 1_800_000_000


class ImmediateThread:
    def __init__(self, *, target, daemon, name):
        assert daemon is True
        self.target = target
        self.name = name

    def start(self):
        self.target()


class DeferredThread(ImmediateThread):
    instances = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.started = False
        self.__class__.instances.append(self)

    def start(self):
        self.started = True


class FailingStartThread(ImmediateThread):
    def start(self):
        raise RuntimeError("thread could not start")


class SwallowingThread(ImmediateThread):
    def start(self):
        try:
            self.target()
        except Exception:
            pass


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount):
        assert amount == 1_000_001
        return self.payload


def version_runner(version="0.144.3"):
    def run(command, **kwargs):
        assert command[-1] == "--version"
        assert kwargs["shell"] is False
        return SimpleNamespace(returncode=0, stdout=f"codex-cli {version}\n", stderr="")

    return run


def manager(tmp_path, **overrides):
    defaults = {
        "executable": "/opt/codex/bin/codex",
        "codex_home": tmp_path / "codex-home",
        "data_dir": tmp_path / "monitor",
        "clock": lambda: NOW,
        "runner": version_runner(),
        "thread_factory": ImmediateThread,
    }
    defaults.update(overrides)
    return UpdateManager(**defaults)


def test_version_parsing_and_comparison_are_numeric_and_prerelease_aware():
    assert parse_version("rust-v0.145.0") == ((0, 145, 0), None)
    assert parse_version("codex-cli 0.144.3") == ((0, 144, 3), None)
    assert parse_version("0.145.0-beta.1") == ((0, 145, 0), "beta.1")
    assert parse_version("v0.145") is None
    assert parse_version("0.145.0 extra") is None
    assert is_newer_version("0.145.0", "0.144.9") is True
    assert is_newer_version("0.145.0", "0.145.0-beta.1") is True
    assert is_newer_version("0.145.0-beta.1", "0.145.0") is False


def test_fresh_codex_version_cache_avoids_network(tmp_path):
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "version.json").write_text(
        json.dumps(
            {
                "latest_version": "0.145.0",
                "last_checked_at": "2027-01-15T08:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    network_calls = []
    updates = manager(
        tmp_path,
        codex_home=codex_home,
        urlopen=lambda *_args, **_kwargs: network_calls.append(True),
    )

    result = updates.check()

    assert network_calls == []
    assert result == {
        "installedVersion": "0.144.3",
        "latestVersion": "0.145.0",
        "updateAvailable": True,
        "checkedAt": NOW,
        "status": "idle",
        "message": None,
    }


def test_stale_cache_fetches_bounded_official_release_with_fixed_headers(tmp_path):
    calls = []

    def urlopen(request, *, timeout):
        calls.append((request, timeout))
        return FakeResponse(b'{"tag_name":"rust-v0.145.0"}')

    updates = manager(tmp_path, urlopen=urlopen)

    result = updates.check(force=True)

    request, timeout = calls[0]
    assert request.full_url == "https://api.github.com/repos/openai/codex/releases/latest"
    assert request.get_header("User-agent") == "Codex-Monitor-Cinnamon/1.2.1"
    assert timeout == 10
    assert result["latestVersion"] == "0.145.0"
    assert result["updateAvailable"] is True


def test_release_fetch_rejects_oversized_malformed_and_prerelease_tags(tmp_path):
    payloads = [
        b"x" * 1_000_001,
        b'{"tag_name":"latest"}',
        b'{"tag_name":"rust-v0.145.0-beta.1"}',
    ]
    for index, payload in enumerate(payloads):
        updates = manager(
            tmp_path / str(index),
            urlopen=lambda *_args, _payload=payload, **_kwargs: FakeResponse(_payload),
        )

        result = updates.check(force=True)

        assert result["latestVersion"] is None
        assert result["updateAvailable"] is False
        assert result["status"] == "idle"


def test_offline_check_retains_last_known_success(tmp_path):
    data_dir = tmp_path / "monitor"
    data_dir.mkdir()
    (data_dir / "update-state.json").write_text(
        json.dumps({"latestVersion": "0.145.0", "checkedAt": NOW - 90_000}),
        encoding="utf-8",
    )
    updates = manager(
        tmp_path,
        data_dir=data_dir,
        urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )

    result = updates.check(force=True)

    assert result["latestVersion"] == "0.145.0"
    assert result["checkedAt"] == NOW - 90_000
    assert result["updateAvailable"] is True
    assert result["message"] is None


def test_successful_check_persists_atomic_private_bounded_state(tmp_path):
    updates = manager(
        tmp_path,
        urlopen=lambda *_args, **_kwargs: FakeResponse(
            b'{"tag_name":"rust-v0.145.0"}'
        ),
    )

    updates.check(force=True)

    state_path = tmp_path / "monitor" / "update-state.json"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted == {"latestVersion": "0.145.0", "checkedAt": NOW}
    assert os.stat(state_path).st_mode & 0o777 == 0o600
    assert list(state_path.parent.glob(".update-state-*.tmp")) == []


def test_malformed_applet_cache_is_ignored(tmp_path):
    data_dir = tmp_path / "monitor"
    data_dir.mkdir()
    (data_dir / "update-state.json").write_text(
        '{"latestVersion":"' + "9" * 500 + '","checkedAt":"private"}',
        encoding="utf-8",
    )
    updates = manager(
        tmp_path,
        data_dir=data_dir,
        urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )

    assert updates.check(force=True)["latestVersion"] is None


def test_oversized_update_caches_are_ignored_without_unbounded_reads(tmp_path):
    codex_home = tmp_path / "codex-home"
    data_dir = tmp_path / "monitor"
    codex_home.mkdir()
    data_dir.mkdir()
    with (codex_home / "version.json").open("wb") as handle:
        handle.truncate(MAX_CACHE_BYTES + 1)
    with (data_dir / "update-state.json").open("wb") as handle:
        handle.truncate(MAX_CACHE_BYTES + 1)

    updates = manager(
        tmp_path,
        codex_home=codex_home,
        data_dir=data_dir,
        urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )

    assert updates.check(force=True)["latestVersion"] is None


def test_nonfinite_update_cache_timestamp_is_ignored(tmp_path):
    data_dir = tmp_path / "monitor"
    data_dir.mkdir()
    (data_dir / "update-state.json").write_text(
        '{"latestVersion":"0.145.0","checkedAt":NaN}', encoding="utf-8"
    )

    updates = manager(
        tmp_path,
        data_dir=data_dir,
        urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )

    assert updates.check(force=True)["latestVersion"] is None


def test_checks_are_nonblocking_and_concurrent_workers_are_rejected(tmp_path):
    DeferredThread.instances = []
    updates = manager(tmp_path, thread_factory=DeferredThread)

    first = updates.check(force=True)
    second = updates.check(force=True)

    assert first["status"] == "checking"
    assert second["status"] == "checking"
    assert len(DeferredThread.instances) == 1
    assert DeferredThread.instances[0].started is True


@pytest.mark.parametrize(
    ("operation", "failure_point", "expected_status"),
    [
        ("check", "factory", "idle"),
        ("check", "start", "idle"),
        ("update", "factory", "failed"),
        ("update", "start", "failed"),
    ],
)
def test_thread_launch_failures_restore_a_terminal_status(
    tmp_path, operation, failure_point, expected_status
):
    def failing_factory(**kwargs):
        if failure_point == "factory":
            raise RuntimeError("thread could not be created")
        return FailingStartThread(**kwargs)

    options = {"thread_factory": failing_factory}
    if operation == "update":
        options["data_dir"] = _available_cache(tmp_path)
    updates = manager(tmp_path, **options)

    method = updates.check if operation == "check" else updates.start
    result = method(**({"force": True} if operation == "check" else {}))

    assert result["status"] == expected_status
    persisted = json.loads(
        (tmp_path / "monitor" / "update-state.json").read_text(encoding="utf-8")
    )
    assert "operation" not in persisted


def _available_cache(tmp_path):
    data_dir = tmp_path / "monitor"
    data_dir.mkdir(parents=True)
    (data_dir / "update-state.json").write_text(
        json.dumps({"latestVersion": "0.145.0", "checkedAt": NOW}),
        encoding="utf-8",
    )
    return data_dir


def test_active_update_is_persisted_and_recovered_by_a_new_manager(tmp_path):
    DeferredThread.instances = []
    data_dir = _available_cache(tmp_path)
    first = manager(tmp_path, data_dir=data_dir, thread_factory=DeferredThread)

    first.start()
    recovered = manager(tmp_path, data_dir=data_dir, thread_factory=DeferredThread)

    persisted = json.loads(
        (data_dir / "update-state.json").read_text(encoding="utf-8")
    )
    assert persisted["operation"]["status"] == "updating"
    assert persisted["operation"]["pid"] == os.getpid()
    assert isinstance(persisted["operation"]["processStart"], str)
    assert recovered.status()["status"] == "updating"
    assert recovered.start()["status"] == "updating"
    assert len(DeferredThread.instances) == 1


def test_dead_update_owner_recovers_as_failed_without_signaling_processes(tmp_path):
    data_dir = _available_cache(tmp_path)
    state_path = data_dir / "update-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["operation"] = {
        "status": "updating",
        "pid": 999_999_999,
        "processStart": "1",
        "startedAt": NOW - 60,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")

    recovered = manager(tmp_path, data_dir=data_dir)

    assert recovered.status()["status"] == "failed"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert "operation" not in persisted


def test_stale_owner_cleanup_does_not_overwrite_a_new_live_operation(
    tmp_path, monkeypatch
):
    DeferredThread.instances = []
    live_dir = _available_cache(tmp_path / "live")
    live_manager = manager(
        tmp_path / "live",
        data_dir=live_dir,
        thread_factory=DeferredThread,
    )
    live_manager.check(force=True)
    live_operation = json.loads(
        (live_dir / "update-state.json").read_text(encoding="utf-8")
    )["operation"]

    data_dir = _available_cache(tmp_path / "target")
    state_path = data_dir / "update-state.json"
    dead_operation = {
        "status": "updating",
        "pid": 999_999_999,
        "processStart": "1",
        "startedAt": NOW - 60,
    }
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["operation"] = dead_operation
    state_path.write_text(json.dumps(state), encoding="utf-8")
    original_persist = UpdateManager._persist_monitor_cache
    raced = False

    def race_before_persist(updates, *args, **kwargs):
        nonlocal raced
        if not raced and updates.data_dir == data_dir:
            raced = True
            replacement = json.loads(state_path.read_text(encoding="utf-8"))
            replacement["operation"] = live_operation
            state_path.write_text(json.dumps(replacement), encoding="utf-8")
        return original_persist(updates, *args, **kwargs)

    monkeypatch.setattr(UpdateManager, "_persist_monitor_cache", race_before_persist)

    recovered = manager(tmp_path / "target", data_dir=data_dir)

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["operation"] == live_operation
    assert recovered.status()["status"] == "checking"


def test_operation_acquisition_adopts_a_newer_live_owner_without_launching(tmp_path, monkeypatch):
    DeferredThread.instances = []
    data_dir = _available_cache(tmp_path)
    contender = manager(tmp_path, data_dir=data_dir, thread_factory=DeferredThread)
    newer_operation = {
        "status": "updating",
        "pid": 424_242,
        "processStart": "222",
        "startedAt": NOW,
    }
    state_path = data_dir / "update-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["operation"] = newer_operation
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(
        UpdateManager,
        "_operation_owner_is_live",
        lambda _self, operation: operation == newer_operation,
    )

    result = contender.check(force=True)

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["operation"] == newer_operation
    assert result["status"] == "updating"
    assert DeferredThread.instances == []


def test_cache_write_does_not_overwrite_an_operation_started_after_reconciliation(
    tmp_path, monkeypatch
):
    data_dir = _available_cache(tmp_path)
    contender = manager(tmp_path, data_dir=data_dir)
    state_path = data_dir / "update-state.json"
    newer_operation = {
        "status": "checking",
        "pid": 424_243,
        "processStart": "223",
        "startedAt": NOW,
    }

    def race_during_cache_read():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["operation"] = newer_operation
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return "0.145.0", NOW

    monkeypatch.setattr(contender, "_read_fresh_codex_cache", race_during_cache_read)
    monkeypatch.setattr(
        contender,
        "_operation_owner_is_live",
        lambda operation: operation == newer_operation,
    )

    contender.check()

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["operation"] == newer_operation


@pytest.mark.parametrize(
    "replaceable_operation",
    [
        {"status": "updating"},
        {
            "status": "checking",
            "pid": 999_999_999,
            "processStart": "1",
            "startedAt": NOW,
        },
    ],
)
def test_operation_acquisition_replaces_malformed_or_dead_owners(
    tmp_path, replaceable_operation
):
    DeferredThread.instances = []
    data_dir = _available_cache(tmp_path)
    contender = manager(tmp_path, data_dir=data_dir, thread_factory=DeferredThread)
    state_path = data_dir / "update-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["operation"] = replaceable_operation
    state_path.write_text(json.dumps(state), encoding="utf-8")

    result = contender.check(force=True)

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["operation"]["status"] == "checking"
    assert persisted["operation"]["pid"] == os.getpid()
    assert result["status"] == "checking"
    assert len(DeferredThread.instances) == 1


@pytest.mark.parametrize(
    ("owner_status", "newer_status"),
    [("checking", "updating"), ("updating", "checking")],
)
def test_older_worker_completion_does_not_clear_a_newer_live_operation(
    tmp_path, monkeypatch, owner_status, newer_status
):
    DeferredThread.instances = []

    def runner(command, **kwargs):
        if command[-1] == "--version":
            return version_runner()(command, **kwargs)
        return SimpleNamespace(returncode=7)

    data_dir = _available_cache(tmp_path)
    owner = manager(
        tmp_path,
        data_dir=data_dir,
        runner=runner,
        thread_factory=DeferredThread,
        urlopen=lambda *_args, **_kwargs: FakeResponse(
            b'{"tag_name":"rust-v0.145.0"}'
        ),
    )
    if owner_status == "checking":
        owner.check(force=True)
    else:
        owner.start()
    state_path = data_dir / "update-state.json"
    older_operation = json.loads(state_path.read_text(encoding="utf-8"))["operation"]
    newer_operation = {
        "status": newer_status,
        "pid": older_operation["pid"] + 1,
        "processStart": str(int(older_operation["processStart"]) + 1),
        "startedAt": NOW,
    }
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["operation"] = newer_operation
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(
        UpdateManager,
        "_operation_owner_is_live",
        lambda _self, operation: operation == newer_operation,
    )

    DeferredThread.instances[0].target()

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["operation"] == newer_operation
    assert owner.status()["status"] == newer_status


def test_install_lock_rejects_a_second_manager_even_without_operation_cache(tmp_path):
    DeferredThread.instances = []
    data_dir = _available_cache(tmp_path)
    first = manager(tmp_path, data_dir=data_dir, thread_factory=DeferredThread)
    first.start()

    (data_dir / "update-state.json").write_text(
        json.dumps({"latestVersion": "0.145.0", "checkedAt": NOW}),
        encoding="utf-8",
    )
    second = manager(tmp_path, data_dir=data_dir, thread_factory=DeferredThread)

    result = second.start()

    assert result["status"] == "updating"
    assert len(DeferredThread.instances) == 1


@pytest.mark.parametrize(
    ("update_returncode", "expected_status", "expected_version"),
    [(0, "updated", "0.145.0"), (7, "failed", "0.144.3")],
)
def test_recovered_manager_observes_external_update_completion(
    tmp_path, update_returncode, expected_status, expected_version
):
    DeferredThread.instances = []
    installed = {"version": "0.144.3"}

    def runner(command, **_kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(
                returncode=0,
                stdout=f"codex-cli {installed['version']}\n",
                stderr="",
            )
        if update_returncode == 0:
            installed["version"] = "0.145.0"
        return SimpleNamespace(returncode=update_returncode)

    data_dir = _available_cache(tmp_path)
    owner = manager(
        tmp_path,
        data_dir=data_dir,
        runner=runner,
        thread_factory=DeferredThread,
    )
    owner.start()
    observer = manager(tmp_path, data_dir=data_dir, runner=runner)
    assert observer.status()["status"] == "updating"

    DeferredThread.instances[0].target()
    result = observer.status()

    assert result["status"] == expected_status
    assert result["installedVersion"] == expected_version


def test_recovered_manager_observes_external_check_completion(tmp_path):
    DeferredThread.instances = []
    owner = manager(
        tmp_path,
        thread_factory=DeferredThread,
        urlopen=lambda *_args, **_kwargs: FakeResponse(
            b'{"tag_name":"rust-v0.145.0"}'
        ),
    )
    owner.check(force=True)
    observer = manager(tmp_path)
    assert observer.status()["status"] == "checking"

    DeferredThread.instances[0].target()
    result = observer.status()

    assert result["status"] == "idle"
    assert result["latestVersion"] == "0.145.0"
    assert result["updateAvailable"] is True


@pytest.mark.parametrize(("operation", "expected_status"), [("check", "idle"), ("update", "failed")])
def test_unexpected_worker_exceptions_restore_terminal_state(
    tmp_path, operation, expected_status
):
    def runner(command, **kwargs):
        if command[-1] == "--version":
            return version_runner()(command, **kwargs)
        raise AssertionError("unexpected worker failure")

    options = {
        "runner": runner,
        "thread_factory": SwallowingThread,
        "urlopen": lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected worker failure")
        ),
    }
    if operation == "update":
        options["data_dir"] = _available_cache(tmp_path)
    updates = manager(tmp_path, **options)

    result = updates.check(force=True) if operation == "check" else updates.start()

    assert result["status"] == expected_status
    persisted = json.loads(
        (tmp_path / "monitor" / "update-state.json").read_text(encoding="utf-8")
    )
    assert "operation" not in persisted


def test_background_update_prefers_codex_self_update_and_rereads_version(tmp_path):
    calls = []
    versions = iter(["0.144.3", "0.145.0"])

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1] == "--version":
            return SimpleNamespace(
                returncode=0, stdout=f"codex-cli {next(versions)}\n", stderr=""
            )
        assert command == ["/opt/codex/bin/codex", "update"]
        assert kwargs["shell"] is False
        assert kwargs["stdout"] == -3
        assert kwargs["stderr"] == -3
        return SimpleNamespace(returncode=0)

    updates = manager(
        tmp_path,
        data_dir=_available_cache(tmp_path),
        runner=runner,
    )

    result = updates.start()

    assert [call[0] for call in calls] == [
        ["/opt/codex/bin/codex", "--version"],
        ["/opt/codex/bin/codex", "update"],
        ["/opt/codex/bin/codex", "--version"],
    ]
    assert result["status"] == "updated"
    assert result["installedVersion"] == "0.145.0"
    assert result["updateAvailable"] is False
    assert result["message"] is None


def test_update_never_downloads_or_executes_an_installer_when_self_update_fails(
    tmp_path,
):
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        if command[-1] == "--version":
            return SimpleNamespace(
                returncode=0, stdout="codex-cli 0.144.3\n", stderr=""
            )
        assert command == ["/opt/codex/bin/codex", "update"]
        assert kwargs["shell"] is False
        return SimpleNamespace(returncode=2)

    network_calls = []

    def urlopen(*args, **kwargs):
        network_calls.append((args, kwargs))
        raise AssertionError("updating must not download executable code")

    updates = manager(
        tmp_path,
        data_dir=_available_cache(tmp_path),
        runner=runner,
        urlopen=urlopen,
    )

    result = updates.start()

    assert commands == [
        ["/opt/codex/bin/codex", "--version"],
        ["/opt/codex/bin/codex", "update"],
    ]
    assert network_calls == []
    assert result["status"] == "failed"
    assert result["message"] is None


def test_update_failure_is_sanitized_and_keeps_installed_version(tmp_path):
    def runner(command, **_kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="codex-cli 0.144.3\n", stderr="")
        return SimpleNamespace(returncode=7, stdout="TOKEN=private", stderr="stack trace")

    updates = manager(
        tmp_path,
        data_dir=_available_cache(tmp_path),
        runner=runner,
        urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("updating must not download executable code")
        ),
    )

    result = updates.start()

    assert result["status"] == "failed"
    assert result["installedVersion"] == "0.144.3"
    assert result["message"] is None
    assert "private" not in repr(result)
    assert "stack" not in repr(result)


def test_invalid_utf8_from_codex_version_is_treated_as_unavailable(tmp_path):
    def runner(_command, **_kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")

    updates = manager(tmp_path, runner=runner)

    assert updates.status()["installedVersion"] is None


def test_default_version_probe_stops_at_a_bounded_stdout_limit(tmp_path, monkeypatch):
    executable = tmp_path / "codex"
    marker = tmp_path / "continued-after-output"
    executable.write_text(
        "#!/usr/bin/python3\n"
        "import os\n"
        "import time\n"
        "os.write(1, b'x' * 131072)\n"
        "time.sleep(2)\n"
        "open(os.environ['VERSION_PROBE_MARKER'], 'w').close()\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("VERSION_PROBE_MARKER", str(marker))

    updates = UpdateManager(executable, tmp_path / "home", tmp_path / "monitor")

    assert updates.status()["installedVersion"] is None
    assert not marker.exists()


def test_update_requires_availability_and_rejects_concurrent_work(tmp_path):
    current = manager(tmp_path)
    try:
        current.start()
    except RuntimeError as error:
        assert str(error) == "No Codex update is available"
    else:
        raise AssertionError("current Codex release unexpectedly started an update")

    DeferredThread.instances = []
    available = manager(
        tmp_path / "available",
        data_dir=_available_cache(tmp_path / "available"),
        thread_factory=DeferredThread,
    )
    first = available.start()
    second = available.start()
    checking = available.check(force=True)

    assert first["status"] == second["status"] == checking["status"] == "updating"
    assert len(DeferredThread.instances) == 1
