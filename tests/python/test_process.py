import io
import json
import subprocess

from codex_bridge.process import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    control_socket_path,
    serve,
    spawn_app_server,
)


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


def test_control_socket_probe_stops_at_a_bounded_stdout_limit(tmp_path, monkeypatch):
    executable = tmp_path / "codex"
    marker = tmp_path / "continued-after-output"
    executable.write_text(
        "#!/usr/bin/python3\n"
        "import os\n"
        "import time\n"
        "os.write(1, b'x' * 131072)\n"
        "time.sleep(2)\n"
        "open(os.environ['CONTROL_PROBE_MARKER'], 'w').close()\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("CONTROL_PROBE_MARKER", str(marker))

    path = control_socket_path(str(executable), codex_home=str(tmp_path / "home"))

    assert path == str(tmp_path / "home" / "app-server-control" / "app-server-control.sock")
    assert not marker.exists()


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


def test_serve_replaces_an_oversized_response_with_a_bounded_error():
    class OversizedRouter:
        def handle(self, request):
            return {
                "id": request["id"],
                "ok": True,
                "data": {"payload": "x" * MAX_RESPONSE_BYTES},
            }

    output_stream = io.StringIO()

    serve(
        OversizedRouter(),
        input_stream=io.StringIO('{"id":"request-1"}\n'),
        output_stream=output_stream,
    )

    raw_response = output_stream.getvalue()
    response = json.loads(raw_response)
    assert len(raw_response.encode("utf-8")) <= MAX_RESPONSE_BYTES
    assert response == {
        "id": "request-1",
        "ok": False,
        "error": {
            "code": "RESPONSE_TOO_LARGE",
            "message": "Codex response was too large",
            "retryable": True,
        },
    }
