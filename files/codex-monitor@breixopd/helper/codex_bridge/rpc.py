"""JSON-RPC client for the local Codex app-server."""

from __future__ import annotations

import json
import threading
import time
from typing import Any


class AppServerClient:
    def __init__(self, *, process, timeout_seconds=10.0):
        self.process = process
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self._responses: dict[int, dict[str, Any]] = {}
        self._condition = threading.Condition()
        self._reader = threading.Thread(target=self._read_responses, daemon=True)
        self._reader.start()

    def initialize(self):
        result = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "codex-monitor-cinnamon",
                    "title": "Codex Monitor",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "experimentalApi": True,
                    "requestAttestation": False,
                },
            },
        )
        self._send({"method": "initialized"})
        return result

    def request(self, method, params=None):
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

        deadline = time.monotonic() + self.timeout_seconds
        with self._condition:
            while request_id not in self._responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Codex request timed out")
                self._condition.wait(timeout=remaining)
            response = self._responses.pop(request_id)

        if "error" in response:
            error = response.get("error") or {}
            code = error.get("code", "unknown")
            raise RuntimeError(f"Codex request failed ({code})")
        return response.get("result")

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=2)

    def _send(self, message: dict[str, Any]):
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        flush = getattr(self.process.stdin, "flush", None)
        if flush:
            flush()

    def _read_responses(self):
        for raw_line in self.process.stdout:
            try:
                message = json.loads(raw_line)
            except (json.JSONDecodeError, TypeError):
                continue
            request_id = message.get("id")
            if not isinstance(request_id, int):
                continue
            with self._condition:
                self._responses[request_id] = message
                self._condition.notify_all()
