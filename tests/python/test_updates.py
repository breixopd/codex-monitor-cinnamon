import json
import os
from types import SimpleNamespace
from urllib.error import URLError

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
    assert request.get_header("User-agent") == "Codex-Monitor-Cinnamon/1.2.0"
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


def _available_cache(tmp_path):
    data_dir = tmp_path / "monitor"
    data_dir.mkdir(parents=True)
    (data_dir / "update-state.json").write_text(
        json.dumps({"latestVersion": "0.145.0", "checkedAt": NOW}),
        encoding="utf-8",
    )
    return data_dir


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
