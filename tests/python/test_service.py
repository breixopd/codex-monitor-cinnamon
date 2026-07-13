from codex_bridge.history import QuotaHistory
from codex_bridge.service import CodexService


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, method, params=None):
        self.calls.append((method, params))
        value = self.responses[method]
        if isinstance(value, Exception):
            raise value
        return value


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
        "email": "developer@example.com",
        "planType": "prolite",
    }
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
