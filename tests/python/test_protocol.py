from codex_bridge.protocol import CommandRouter
from codex_bridge.remote import RemoteDaemonStuckError


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

    def remote_repair(self):
        self.calls.append(("remote_repair", None))
        return {"status": "connected"}

    def remote_pair_start(self):
        self.calls.append(("remote_pair_start", None))
        return {
            "pairingCode": "opaque-code",
            "manualPairingCode": "ABCD-EFGH",
            "environmentId": "environment-1",
            "expiresAt": 1_800_000_000,
        }

    def remote_pair_status(self, pairing_code, manual_pairing_code):
        self.calls.append(("remote_pair_status", pairing_code, manual_pairing_code))
        return {"claimed": False}

    def remote_clients(self, environment_id):
        self.calls.append(("remote_clients", environment_id))
        return {"clients": []}

    def remote_revoke(self, environment_id, client_id):
        self.calls.append(("remote_revoke", environment_id, client_id))
        return {"revoked": True}

    def sessions(self, limit):
        self.calls.append(("sessions", limit))
        return {"active": [], "recent": []}

    def open_codex(self):
        self.calls.append(("open_codex", None))
        return {"launched": True}

    def open_session(self, thread_id, cwd):
        self.calls.append(("open_session", thread_id, cwd))
        return {"launched": True}

    def update_status(self):
        self.calls.append(("update_status", None))
        return {"status": "idle", "updateAvailable": True}

    def update_check(self, force=False):
        self.calls.append(("update_check", force))
        return {"status": "checking", "updateAvailable": True}

    def update_start(self):
        self.calls.append(("update_start", None))
        return {"status": "updating", "updateAvailable": True}


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


def test_router_exposes_remote_status_and_rejects_retired_pair_alias():
    router = CommandRouter(FakeService())

    status = router.handle(
        {"id": "request-5", "action": "remote_status", "params": {}}
    )
    retired = router.handle(
        {"id": "request-6", "action": "remote_pair", "params": {}}
    )

    assert status["data"] == {"status": "connected"}
    assert retired["error"]["code"] == "INVALID_ACTION"


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


def test_router_requires_confirmation_before_stopping_remote_control():
    router = CommandRouter(FakeService())

    denied = router.handle(
        {"id": "request-stop-1", "action": "remote_stop", "params": {}}
    )
    allowed = router.handle(
        {
            "id": "request-stop-2",
            "action": "remote_stop",
            "params": {"confirmed": True},
        }
    )

    assert denied["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert allowed["data"] == {"status": "disabled"}


def test_router_requires_confirmation_before_repairing_remote_control():
    service = FakeService()
    router = CommandRouter(service)

    denied = router.handle(
        {"id": "request-repair-1", "action": "remote_repair", "params": {}}
    )
    allowed = router.handle(
        {
            "id": "request-repair-2",
            "action": "remote_repair",
            "params": {"confirmed": True},
        }
    )

    assert denied["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert allowed["data"] == {"status": "connected"}
    assert service.calls == [("remote_repair", None)]


def test_router_exposes_only_the_safe_stuck_daemon_error_code():
    class StuckService(FakeService):
        def remote_start(self):
            raise RemoteDaemonStuckError("private daemon path")

    response = CommandRouter(StuckService()).handle(
        {
            "id": "request-stuck",
            "action": "remote_start",
            "params": {"confirmed": True},
        }
    )

    assert response["error"] == {
        "code": "REMOTE_DAEMON_STUCK",
        "message": "Codex Remote background service is stuck",
        "retryable": False,
    }
    assert "private" not in repr(response)


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


def test_router_exposes_validated_update_status_check_and_confirmed_start():
    service = FakeService()
    router = CommandRouter(service)

    status = router.handle({"id": "update-1", "action": "update_status", "params": {}})
    check = router.handle(
        {
            "id": "update-2",
            "action": "update_check",
            "params": {"force": True},
        }
    )
    denied = router.handle(
        {"id": "update-3", "action": "update_start", "params": {}}
    )
    started = router.handle(
        {
            "id": "update-4",
            "action": "update_start",
            "params": {"confirmed": True},
        }
    )

    assert status["data"]["status"] == "idle"
    assert check["data"]["status"] == "checking"
    assert denied["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert started["data"]["status"] == "updating"
    assert service.calls == [
        ("update_status", None),
        ("update_check", True),
        ("update_start", None),
    ]


def test_router_rejects_unknown_or_mistyped_update_parameters():
    router = CommandRouter(FakeService())
    requests = [
        {"id": "bad-status", "action": "update_status", "params": {"extra": True}},
        {"id": "bad-check", "action": "update_check", "params": {"force": "yes"}},
        {
            "id": "bad-start",
            "action": "update_start",
            "params": {"confirmed": True, "extra": True},
        },
    ]

    for request in requests:
        assert router.handle(request)["error"]["code"] == "INVALID_PARAMS"


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


def test_router_exposes_remote_pairing_status_clients_and_confirmed_revoke():
    service = FakeService()
    router = CommandRouter(service)

    started = router.handle(
        {"id": "remote-1", "action": "remote_pair_start", "params": {}}
    )
    claimed = router.handle(
        {
            "id": "remote-2",
            "action": "remote_pair_status",
            "params": {
                "pairingCode": "opaque-code",
                "manualPairingCode": "ABCD-EFGH",
            },
        }
    )
    clients = router.handle(
        {
            "id": "remote-3",
            "action": "remote_clients",
            "params": {"environmentId": "environment-1"},
        }
    )
    revoked = router.handle(
        {
            "id": "remote-4",
            "action": "remote_revoke",
            "params": {
                "environmentId": "environment-1",
                "clientId": "client-1",
                "confirmed": True,
            },
        }
    )

    assert started["data"]["pairingCode"] == "opaque-code"
    assert claimed["data"] == {"claimed": False}
    assert clients["data"] == {"clients": []}
    assert revoked["data"] == {"revoked": True}
    assert service.calls == [
        ("remote_pair_start", None),
        ("remote_pair_status", "opaque-code", "ABCD-EFGH"),
        ("remote_clients", "environment-1"),
        ("remote_revoke", "environment-1", "client-1"),
    ]


def test_router_validates_remote_identifiers_codes_and_revoke_confirmation():
    router = CommandRouter(FakeService())
    invalid_requests = [
        {
            "id": "pair-empty",
            "action": "remote_pair_status",
            "params": {},
        },
        {
            "id": "environment-empty",
            "action": "remote_clients",
            "params": {"environmentId": ""},
        },
        {
            "id": "client-long",
            "action": "remote_revoke",
            "params": {
                "environmentId": "environment-1",
                "clientId": "x" * 257,
                "confirmed": True,
            },
        },
    ]
    for request in invalid_requests:
        assert router.handle(request)["error"]["code"] == "INVALID_PARAMS"

    unconfirmed = router.handle(
        {
            "id": "revoke-unconfirmed",
            "action": "remote_revoke",
            "params": {"environmentId": "environment-1", "clientId": "client-1"},
        }
    )
    assert unconfirmed["error"]["code"] == "CONFIRMATION_REQUIRED"
