from codex_bridge.protocol import CommandRouter


class FakeService:
    def snapshot(self):
        return {"capturedAt": 10}

    def consume_reset(self, credit_id, idempotency_key):
        return {"creditId": credit_id, "idempotencyKey": idempotency_key}


def test_router_returns_correlated_success_response():
    router = CommandRouter(FakeService())

    response = router.handle({"id": "request-1", "action": "snapshot", "params": {}})

    assert response == {
        "id": "request-1",
        "ok": True,
        "data": {"capturedAt": 10},
    }


def test_router_rejects_unknown_action_without_echoing_untrusted_details():
    router = CommandRouter(FakeService())

    response = router.handle(
        {"id": "request-2", "action": "run arbitrary command", "params": {}}
    )

    assert response == {
        "id": "request-2",
        "ok": False,
        "error": {
            "code": "INVALID_ACTION",
            "message": "Unsupported Codex Monitor action",
            "retryable": False,
        },
    }


def test_router_requires_valid_uuid_for_reset_attempt():
    router = CommandRouter(FakeService())

    response = router.handle(
        {
            "id": "request-3",
            "action": "consume_reset",
            "params": {"creditId": "credit-1", "idempotencyKey": "not-a-uuid"},
        }
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_PARAMS"
