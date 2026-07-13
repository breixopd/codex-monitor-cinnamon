"""Validated JSONL command protocol exposed to the Cinnamon applet."""

from __future__ import annotations

import uuid


def _error(request_id, code, message, *, retryable=False):
    return {
        "id": request_id,
        "ok": False,
        "error": {"code": code, "message": message, "retryable": retryable},
    }


class CommandRouter:
    def __init__(self, service):
        self.service = service

    def handle(self, request):
        request_id = request.get("id") if isinstance(request, dict) else None
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            return _error(None, "INVALID_REQUEST", "Invalid request identifier")

        action = request.get("action")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return _error(request_id, "INVALID_PARAMS", "Invalid action parameters")

        try:
            if action == "snapshot":
                data = self.service.snapshot()
            elif action == "consume_reset":
                credit_id = params.get("creditId")
                idempotency_key = params.get("idempotencyKey")
                if not self._valid_credit_id(credit_id) or not self._valid_uuid(
                    idempotency_key
                ):
                    return _error(
                        request_id, "INVALID_PARAMS", "Invalid reset-credit parameters"
                    )
                if params.get("confirmed") is not True:
                    return _error(
                        request_id,
                        "CONFIRMATION_REQUIRED",
                        "Explicit confirmation is required",
                    )
                data = self.service.consume_reset(credit_id, idempotency_key)
            elif action == "remote_status":
                data = self.service.remote_status()
            elif action == "remote_start":
                if params.get("confirmed") is not True:
                    return _error(
                        request_id,
                        "CONFIRMATION_REQUIRED",
                        "Explicit confirmation is required",
                    )
                data = self.service.remote_start()
            elif action == "remote_stop":
                data = self.service.remote_stop()
            elif action == "remote_pair":
                data = self.service.remote_pair()
            else:
                return _error(
                    request_id,
                    "INVALID_ACTION",
                    "Unsupported Codex Monitor action",
                )
        except TimeoutError:
            return _error(
                request_id, "CODEX_TIMEOUT", "Codex did not respond", retryable=True
            )
        except RuntimeError:
            return _error(
                request_id, "CODEX_ERROR", "Codex request failed", retryable=True
            )
        return {"id": request_id, "ok": True, "data": data}

    @staticmethod
    def _valid_credit_id(value):
        return isinstance(value, str) and 0 < len(value) <= 256

    @staticmethod
    def _valid_uuid(value):
        if not isinstance(value, str):
            return False
        try:
            return str(uuid.UUID(value)) == value.lower()
        except (ValueError, AttributeError):
            return False
