from codex_bridge.protocol import CommandRouter


class FakeService:
    def __init__(self):
        self.calls = []

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

    def sessions(self, limit):
        self.calls.append(("sessions", limit))
        return {"active": [], "recent": []}

    def open_codex(self):
        self.calls.append(("open_codex", None))
        return {"launched": True}

    def open_session(self, thread_id, cwd):
        self.calls.append(("open_session", thread_id, cwd))
        return {"launched": True}


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


def test_router_exposes_bounded_sessions_and_launch_actions():
    service = FakeService()
    router = CommandRouter(service)
    thread_id = "019c0000-0000-7000-8000-000000000001"

    sessions = router.handle(
        {"id": "request-9", "action": "sessions", "params": {"limit": 12}}
    )
    opened = router.handle(
        {"id": "request-10", "action": "open_codex", "params": {}}
    )
    resumed = router.handle(
        {
            "id": "request-11",
            "action": "open_session",
            "params": {"threadId": thread_id, "cwd": "/tmp"},
        }
    )

    assert sessions["data"] == {"active": [], "recent": []}
    assert opened["data"] == {"launched": True}
    assert resumed["data"] == {"launched": True}
    assert service.calls == [
        ("sessions", 12),
        ("open_codex", None),
        ("open_session", thread_id, "/tmp"),
    ]


def test_router_rejects_invalid_session_limits_ids_and_paths():
    router = CommandRouter(FakeService())

    requests = [
        {"id": "bad-limit", "action": "sessions", "params": {"limit": 0}},
        {
            "id": "bad-id",
            "action": "open_session",
            "params": {"threadId": "not-a-uuid", "cwd": "/tmp"},
        },
        {
            "id": "bad-path",
            "action": "open_session",
            "params": {
                "threadId": "019c0000-0000-7000-8000-000000000001",
                "cwd": "x" * 4097,
            },
        },
        {"id": "bad-open", "action": "open_codex", "params": {"extra": True}},
    ]

    for request in requests:
        response = router.handle(request)
        assert response["error"]["code"] == "INVALID_PARAMS"
