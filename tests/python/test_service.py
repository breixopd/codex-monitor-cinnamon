from codex_bridge.history import QuotaHistory
from codex_bridge.service import CodexService


class FakeClient:
    def __init__(self, responses, notifications=None):
        self.responses = responses
        self.notifications = notifications or {}
        self.calls = []

    def request(self, method, params=None):
        self.calls.append((method, params))
        value = self.responses[method]
        if isinstance(value, Exception):
            raise value
        return value

    def wait_for_notification(self, method, *, timeout_seconds):
        return self.notifications.get(method)


def _rate_limits():
    return {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 25,
                "windowDurationMins": 300,
                "resetsAt": 1_800_000_000,
            },
            "secondary": {
                "usedPercent": 40,
                "windowDurationMins": 10080,
                "resetsAt": 1_800_500_000,
            },
            "planType": "prolite",
        },
        "rateLimitsByLimitId": None,
        "rateLimitResetCredits": {"availableCount": 0, "credits": []},
    }


def test_snapshot_combines_account_limits_usage_and_history(tmp_path):
    client = FakeClient(
        {
            "account/read": {
                "account": {
                    "type": "chatgpt",
                    "email": "developer@example.com",
                    "planType": "prolite",
                },
                "requiresOpenaiAuth": False,
            },
            "account/rateLimits/read": _rate_limits(),
            "account/usage/read": {
                "summary": {"lifetimeTokens": 1234, "currentStreakDays": 3},
                "dailyUsageBuckets": [{"startDate": "2026-07-13", "tokens": 250}],
            },
        }
    )
    history = QuotaHistory(tmp_path / "history.jsonl", retention_days=30)
    service = CodexService(client, history, clock=lambda: 1_799_100_000)

    snapshot = service.snapshot()

    assert snapshot["account"] == {
        "type": "chatgpt",
        "planType": "prolite",
    }
    assert "developer@example.com" not in repr(snapshot)
    assert snapshot["tokenUsage"]["dailyUsageBuckets"][0]["tokens"] == 250
    assert snapshot["history"][0]["fiveHourUsedPercent"] == 25.0


def test_snapshot_treats_account_usage_as_optional_for_older_codex(tmp_path):
    client = FakeClient(
        {
            "account/read": {"account": {"type": "apiKey"}, "requiresOpenaiAuth": False},
            "account/rateLimits/read": _rate_limits(),
            "account/usage/read": RuntimeError("Codex request failed (-32601)"),
        }
    )
    service = CodexService(
        client,
        QuotaHistory(tmp_path / "history.jsonl", retention_days=30),
        clock=lambda: 1_799_100_000,
    )

    snapshot = service.snapshot()

    assert snapshot["tokenUsage"] is None
    assert snapshot["capabilities"]["activity"] is False
    assert snapshot["capabilities"]["resetCredits"] is True


def test_snapshot_discards_malformed_optional_usage_fields(tmp_path):
    client = FakeClient(
        {
            "account/read": {
                "account": {
                    "type": {"private": "discard"},
                    "planType": {"private": "discard"},
                }
            },
            "account/rateLimits/read": _rate_limits(),
            "account/usage/read": {
                "summary": {"lifetimeTokens": "not-a-number", "private": "discard"},
                "dailyUsageBuckets": [
                    {"startDate": "2026-07-13", "tokens": 250},
                    {"startDate": "2026-07-14"},
                    {"startDate": {"private": "discard"}, "tokens": 999},
                ],
            },
        }
    )
    service = CodexService(client, history=None, clock=lambda: 1_799_100_000)

    snapshot = service.snapshot()

    assert snapshot["tokenUsage"] == {
        "summary": {},
        "dailyUsageBuckets": [{"startDate": "2026-07-13", "tokens": 250}],
    }
    assert snapshot["account"] is None
    assert "private" not in repr(snapshot)


def test_snapshot_bounds_and_type_checks_daily_usage_buckets():
    usage = CodexService._normalize_token_usage(
        {
            "dailyUsageBuckets": [
                *(
                    {"startDate": f"2025-01-{(index % 28) + 1:02d}", "tokens": index}
                    for index in range(400)
                ),
                {"startDate": "2026-07-16", "tokens": 999},
            ]
        }
    )

    assert len(usage["dailyUsageBuckets"]) == 366
    assert usage["dailyUsageBuckets"][-1]["tokens"] == 365
    assert CodexService._normalize_token_usage(
        {"dailyUsageBuckets": "not-a-list"}
    ) == {"summary": {}, "dailyUsageBuckets": []}
    huge = CodexService._normalize_token_usage(
        {"dailyUsageBuckets": [{"startDate": "2026-07-16", "tokens": 10**30}]}
    )
    assert huge["dailyUsageBuckets"][0]["tokens"] == 9_007_199_254_740_991


def test_snapshot_merges_the_latest_sparse_rate_limit_update(tmp_path):
    initial = _rate_limits()
    initial["rateLimits"]["secondary"]["usedPercent"] = 0
    client = FakeClient(
        {
            "account/read": {"account": {"type": "chatgpt", "planType": "prolite"}},
            "account/rateLimits/read": initial,
            "account/usage/read": {"summary": {}, "dailyUsageBuckets": []},
        },
        notifications={
            "account/rateLimits/updated": {
                "rateLimits": {
                    "limitId": "codex",
                    "secondary": {"usedPercent": 37},
                }
            }
        },
    )
    service = CodexService(
        client,
        QuotaHistory(tmp_path / "history.jsonl", retention_days=30),
        clock=lambda: 1_799_100_000,
    )

    snapshot = service.snapshot()

    assert snapshot["windows"]["weekly"]["usedPercent"] == 37.0
    assert snapshot["windows"]["weekly"]["resetsAt"] == 1_800_500_000


def test_snapshot_does_not_replace_canonical_limits_with_a_foreign_notification(
    tmp_path,
):
    client = FakeClient(
        {
            "account/read": {"account": {"type": "chatgpt", "planType": "prolite"}},
            "account/rateLimits/read": _rate_limits(),
            "account/usage/read": {"summary": {}, "dailyUsageBuckets": []},
        },
        notifications={
            "account/rateLimits/updated": {
                "rateLimits": {
                    "limitId": "codex_bengalfox",
                    "limitName": "GPT-5.3-Codex-Spark",
                    "primary": {
                        "usedPercent": 0,
                        "windowDurationMins": 10080,
                        "resetsAt": 1_800_604_800,
                    },
                }
            }
        },
    )
    service = CodexService(
        client,
        QuotaHistory(tmp_path / "history.jsonl", retention_days=30),
        clock=lambda: 1_799_100_000,
    )

    snapshot = service.snapshot()

    assert snapshot["windows"]["weekly"]["limitId"] == "codex"
    assert snapshot["windows"]["weekly"]["usedPercent"] == 40.0


def test_consume_reset_sends_credit_and_idempotency_key():
    client = FakeClient(
        {"account/rateLimitResetCredit/consume": {"outcome": "reset"}}
    )
    service = CodexService(client, history=None, clock=lambda: 1_799_100_000)

    result = service.consume_reset("credit-1", "123e4567-e89b-12d3-a456-426614174000")

    assert result == {"outcome": "reset"}
    assert client.calls == [
        (
            "account/rateLimitResetCredit/consume",
            {
                "creditId": "credit-1",
                "idempotencyKey": "123e4567-e89b-12d3-a456-426614174000",
            },
        )
    ]


def test_sessions_request_recent_threads_and_normalize_response():
    thread_id = "019c0000-0000-7000-8000-000000000001"
    client = FakeClient(
        {
            "thread/list": {
                "data": [
                    {
                        "id": thread_id,
                        "preview": "Recent work",
                        "cwd": "/home/user/Code/Widgets",
                        "source": "cli",
                        "status": {"type": "notLoaded"},
                        "createdAt": 100,
                        "updatedAt": 200,
                    }
                ]
            }
        }
    )
    service = CodexService(client, history=None)

    result = service.sessions(12)

    assert result["recent"][0]["id"] == thread_id
    assert client.calls == [
        (
            "thread/list",
            {"limit": 12, "sortKey": "updated_at", "sortDirection": "desc"},
        )
    ]


def test_launch_operations_are_delegated_to_terminal_launcher():
    class FakeLauncher:
        def __init__(self):
            self.calls = []

        def open_codex(self):
            self.calls.append(("codex", None))
            return {"launched": True}

        def open_session(self, thread_id, cwd):
            self.calls.append((thread_id, cwd))
            return {"launched": True}

    launcher = FakeLauncher()
    service = CodexService(None, history=None, launcher=launcher)
    thread_id = "019c0000-0000-7000-8000-000000000001"

    assert service.open_codex() == {"launched": True}
    assert service.open_session(thread_id, "/tmp") == {"launched": True}
    assert launcher.calls == [("codex", None), (thread_id, "/tmp")]


def test_remote_operations_are_delegated_to_remote_controller():
    class FakeRemote:
        def status(self):
            return {"status": "connected"}

        def start(self):
            return {"status": "connected"}

        def stop(self):
            return {"status": "disabled"}

        def repair(self):
            return {"status": "connected"}

        def pair_start(self):
            return {
                "pairingCode": "opaque",
                "manualPairingCode": "ABCD-EFGH",
                "environmentId": "environment-1",
                "expiresAt": 1_800_000_000,
            }

        def pair_status(self, pairing_code, manual_pairing_code):
            return {"claimed": pairing_code == "opaque"}

        def clients(self, environment_id):
            return {"clients": [{"clientId": f"client@{environment_id}"}]}

        def revoke(self, environment_id, client_id):
            return {"revoked": bool(environment_id and client_id)}

    service = CodexService(
        client=None,
        history=None,
        remote=FakeRemote(),
        clock=lambda: 1_799_100_000,
    )

    assert service.remote_status() == {"status": "connected"}
    assert service.remote_start() == {"status": "connected"}
    assert service.remote_stop() == {"status": "disabled"}
    assert service.remote_repair() == {"status": "connected"}
    assert service.remote_pair_start()["environmentId"] == "environment-1"
    assert service.remote_pair_status("opaque", "ABCD-EFGH") == {"claimed": True}
    assert service.remote_clients("environment-1")["clients"][0]["clientId"] == (
        "client@environment-1"
    )
    assert service.remote_revoke("environment-1", "client-1") == {"revoked": True}


def test_update_operations_are_delegated_to_update_manager():
    class FakeUpdates:
        def __init__(self):
            self.calls = []

        def status(self):
            self.calls.append(("status", None))
            return {"status": "idle"}

        def check(self, *, force=False):
            self.calls.append(("check", force))
            return {"status": "checking"}

        def start(self):
            self.calls.append(("start", None))
            return {"status": "updating"}

    updates = FakeUpdates()
    service = CodexService(None, None, updates=updates)

    assert service.update_status() == {"status": "idle"}
    assert service.update_check(force=True) == {"status": "checking"}
    assert service.update_start() == {"status": "updating"}
    assert updates.calls == [("status", None), ("check", True), ("start", None)]
