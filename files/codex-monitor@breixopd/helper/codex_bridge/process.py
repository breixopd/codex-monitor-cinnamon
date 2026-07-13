"""Process creation and JSONL serving for Codex Monitor."""

from __future__ import annotations

import json
import os
import subprocess


MAX_REQUEST_BYTES = 1_000_000


def spawn_app_server(executable, *, codex_home=None, proxy=False, popen=None, base_env=None):
    popen = popen or subprocess.Popen
    command = (
        [executable, "app-server", "proxy"]
        if proxy
        else [
            executable,
            "-s",
            "read-only",
            "-a",
            "untrusted",
            "app-server",
        ]
    )
    environment = dict(os.environ if base_env is None else base_env)
    if codex_home:
        environment["CODEX_HOME"] = codex_home
    return popen(
        command,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env=environment,
        close_fds=True,
    )


def serve(router, *, input_stream, output_stream):
    for raw_line in input_stream:
        try:
            if len(raw_line.encode("utf-8")) > MAX_REQUEST_BYTES:
                raise ValueError("request too large")
            request = json.loads(raw_line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
        except (json.JSONDecodeError, UnicodeError, ValueError):
            response = {
                "id": None,
                "ok": False,
                "error": {
                    "code": "INVALID_JSON",
                    "message": "Invalid JSON request",
                    "retryable": False,
                },
            }
        else:
            response = router.handle(request)
        output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
        output_stream.flush()
