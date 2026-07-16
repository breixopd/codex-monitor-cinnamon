import io
import json
import subprocess

from codex_bridge.process import MAX_REQUEST_BYTES, control_socket_path, serve, spawn_app_server


class FakePopen:
    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return object()


def test_spawn_app_server_uses_fixed_arguments_and_scoped_codex_home():
    popen = FakePopen()

    process = spawn_app_server(
        "/opt/codex/bin/codex",
        codex_home="/home/user/.codex-work",
        popen=popen,
        base_env={"PATH": "/usr/bin"},
    )

    assert process is not None
    command, kwargs = popen.calls[0]
    assert command == [
        "/opt/codex/bin/codex",
        "-s",
        "read-only",
        "-a",
        "untrusted",
        "app-server",
    ]
    assert kwargs["shell"] is False
    assert kwargs["env"] == {
        "PATH": "/usr/bin",
        "CODEX_HOME": "/home/user/.codex-work",
    }


def test_control_socket_path_uses_daemon_advertisement_and_scoped_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {"status": "running", "socketPath": "~/.codex/control.sock"}
            ),
            stderr="private",
        )

    path = control_socket_path(
        "/opt/codex/bin/codex",
        codex_home="/home/user/.codex-work",
        runner=runner,
        base_env={"PATH": "/usr/bin"},
    )

    assert path == str(tmp_path / ".codex" / "control.sock")
    assert calls[0][0] == [
        "/opt/codex/bin/codex",
        "app-server",
        "daemon",
        "version",
    ]
    assert calls[0][1] == {
        "shell": False,
        "check": False,
        "capture_output": True,
        "text": True,
        "timeout": 5,
        "env": {"PATH": "/usr/bin", "CODEX_HOME": "/home/user/.codex-work"},
    }


def test_control_socket_path_falls_back_to_codex_home_without_exposing_errors():
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="private diagnostic"
        )

    path = control_socket_path(
        "codex", codex_home="/home/user/.codex-work", runner=runner, base_env={}
    )

    assert path == "/home/user/.codex-work/app-server-control/app-server-control.sock"


def test_serve_keeps_protocol_jsonl_and_survives_malformed_input():
    class FakeRouter:
        def handle(self, request):
            return {"id": request.get("id"), "ok": True, "data": {}}

    input_stream = io.StringIO('not-json\n{"id":"request-1"}\n')
    output_stream = io.StringIO()

    serve(FakeRouter(), input_stream=input_stream, output_stream=output_stream)

    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == "INVALID_JSON"
    assert responses[1] == {"id": "request-1", "ok": True, "data": {}}


def test_serve_discards_an_oversized_line_and_keeps_the_stream_aligned():
    class FakeRouter:
        def handle(self, request):
            return {"id": request.get("id"), "ok": True, "data": {}}

    input_stream = io.StringIO(
        "x" * (MAX_REQUEST_BYTES + 50) + '\n{"id":"request-2"}\n'
    )
    output_stream = io.StringIO()

    serve(FakeRouter(), input_stream=input_stream, output_stream=output_stream)

    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == "INVALID_JSON"
    assert responses[1] == {"id": "request-2", "ok": True, "data": {}}
