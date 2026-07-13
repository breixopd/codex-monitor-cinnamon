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


def test_create_runtime_wires_main_client_history_and_proxy_factory(tmp_path):
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

    runtime = create_runtime(
        options, spawn=spawn, client_factory=client_factory, remote_runner=lambda *a, **k: None
    )

    assert clients[0].initialized is True
    assert processes[0]["proxy"] is False
    assert runtime.history.path == tmp_path / "history.jsonl"
    assert runtime.remote.environment["CODEX_HOME"] == "/home/user/.codex"

    proxy_client = runtime.remote.client_factory()
    assert processes[1]["proxy"] is True
    assert proxy_client.process == processes[1]
