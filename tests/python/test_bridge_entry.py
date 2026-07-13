from types import SimpleNamespace

from bridge import create_runtime


class FakeClient:
    def __init__(self, process):
        self.process = process
        self.initialized = False
        self.closed = False

    def initialize(self):
        self.initialized = True

    def close(self):
        self.closed = True


def test_create_runtime_wires_main_client_history_and_unix_socket_factory(tmp_path):
    processes = []

    def spawn(executable, **kwargs):
        process = {"executable": executable, **kwargs}
        processes.append(process)
        return process

    clients = []

    def client_factory(process):
        client = FakeClient(process)
        clients.append(client)
        return client

    options = SimpleNamespace(
        codex="codex",
        codex_home="/home/user/.codex",
        data_dir=str(tmp_path),
        history_days=30,
    )

    remote_clients = []

    def remote_client_factory(socket_path):
        remote_client = SimpleNamespace(socket_path=socket_path)
        remote_clients.append(remote_client)
        return remote_client

    socket_resolver_calls = []

    def socket_resolver(executable, **kwargs):
        socket_resolver_calls.append((executable, kwargs))
        return "/home/user/.codex/app-server-control/control.sock"

    runtime = create_runtime(
        options,
        spawn=spawn,
        client_factory=client_factory,
        remote_client_factory=remote_client_factory,
        socket_resolver=socket_resolver,
        remote_runner=lambda *a, **k: None,
    )

    assert clients[0].initialized is True
    assert len(processes) == 1
    assert runtime.history.path == tmp_path / "history.jsonl"
    assert runtime.remote.environment["CODEX_HOME"] == "/home/user/.codex"

    control_client = runtime.remote.client_factory()
    assert control_client.socket_path == (
        "/home/user/.codex/app-server-control/control.sock"
    )
    assert remote_clients == [control_client]
    assert socket_resolver_calls == [
        (
            "codex",
            {
                "codex_home": "/home/user/.codex",
                "runner": runtime.remote.runner,
                "base_env": runtime.remote.environment,
            },
        )
    ]


def test_create_runtime_wires_one_update_manager_without_starting_a_check(tmp_path):
    options = SimpleNamespace(
        codex="/opt/codex/bin/codex",
        codex_home="/home/user/.codex",
        data_dir=str(tmp_path),
        history_days=30,
    )
    calls = []
    update_manager = SimpleNamespace(status=lambda: {"status": "idle"})

    def update_manager_factory(executable, codex_home, data_dir):
        calls.append((executable, codex_home, data_dir))
        return update_manager

    runtime = create_runtime(
        options,
        spawn=lambda *_args, **_kwargs: object(),
        client_factory=FakeClient,
        update_manager_factory=update_manager_factory,
    )

    assert calls == [
        ("/opt/codex/bin/codex", "/home/user/.codex", str(tmp_path))
    ]
    assert runtime.updates is update_manager
    assert runtime.service.updates is update_manager
