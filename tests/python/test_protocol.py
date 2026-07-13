from codex_bridge.protocol import CommandRouter


class FakeService:
    def snapshot(self):
        return {"capturedAt": 10}

    def consume_reset(self, credit_id, idempotency_key):
        return {"creditId": credit_id, "idempotencyKey": idempotency_key}

    def remote_status(self):
        return {"status": "connected"}

    def remote_start(self):
        return {"status": "connected"}

    def remote_stop(self):
        return {"status": "disabled"}

    def remote_pair(self):
        return {"manualPairingCode": "ABCD-EFGH", "expiresAt": 1_800_000_000}


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


def test_router_requires_explicit_confirmation_for_destructive_actions():
    router = CommandRouter(FakeService())

    response = router.handle(
        {
            "id": "request-4",
            "action": "consume_reset",
            "params": {
                "creditId": "credit-1",
                "idempotencyKey": "123e4567-e89b-12d3-a456-426614174000",
            },
        }
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_router_exposes_remote_status_and_pairing():
    router = CommandRouter(FakeService())

    status = router.handle(
        {"id": "request-5", "action": "remote_status", "params": {}}
    )
    pair = router.handle({"id": "request-6", "action": "remote_pair", "params": {}})

    assert status["data"] == {"status": "connected"}
    assert pair["data"]["manualPairingCode"] == "ABCD-EFGH"


def test_router_requires_confirmation_before_starting_remote_control():
    router = CommandRouter(FakeService())

    denied = router.handle(
        {"id": "request-7", "action": "remote_start", "params": {}}
    )
    allowed = router.handle(
        {
            "id": "request-8",
            "action": "remote_start",
            "params": {"confirmed": True},
        }
    )

    assert denied["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert allowed["data"] == {"status": "connected"}
