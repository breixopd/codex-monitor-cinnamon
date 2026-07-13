import io
import json

from codex_bridge.process import serve, spawn_app_server


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


def test_spawn_proxy_uses_control_socket_transport_arguments():
    popen = FakePopen()

    spawn_app_server("codex", proxy=True, popen=popen, base_env={})

    assert popen.calls[0][0] == ["codex", "app-server", "proxy"]


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
