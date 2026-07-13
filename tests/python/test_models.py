from codex_bridge.models import normalize_snapshot


def test_normalize_snapshot_classifies_windows_by_duration_not_position():
    payload = {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": 41,
                "windowDurationMins": 10080,
                "resetsAt": 1_800_000_000,
            },
            "secondary": {
                "usedPercent": 27,
                "windowDurationMins": 300,
                "resetsAt": 1_799_500_000,
            },
            "planType": "prolite",
        },
        "rateLimitsByLimitId": None,
        "rateLimitResetCredits": {
            "availableCount": 1,
            "credits": [
                {
                    "id": "credit-1",
                    "resetType": "codexRateLimits",
                    "status": "available",
                    "grantedAt": 1_799_000_000,
                    "expiresAt": 1_801_000_000,
                    "title": "Full reset",
                    "description": "Restores Codex limits",
                }
            ],
        },
    }

    snapshot = normalize_snapshot(payload, captured_at=1_799_100_000)

    assert snapshot["capturedAt"] == 1_799_100_000
    assert snapshot["planType"] == "prolite"
    assert snapshot["windows"]["fiveHour"]["usedPercent"] == 27.0
    assert snapshot["windows"]["weekly"]["usedPercent"] == 41.0
    assert snapshot["resetCredits"]["availableCount"] == 1
    assert snapshot["resetCredits"]["credits"][0]["expiresAt"] == 1_801_000_000


def test_normalize_snapshot_preserves_unknown_windows_without_mislabeling():
    payload = {
        "rateLimits": {
            "limitId": "codex-spark",
            "limitName": "Codex Spark",
            "primary": {
                "usedPercent": 12,
                "windowDurationMins": 1440,
                "resetsAt": 1_800_000_000,
            },
            "secondary": None,
            "planType": "pro",
        },
        "rateLimitsByLimitId": None,
        "rateLimitResetCredits": None,
    }

    snapshot = normalize_snapshot(payload, captured_at=1_799_100_000)

    assert snapshot["windows"]["fiveHour"] is None
    assert snapshot["windows"]["weekly"] is None
    assert snapshot["extraWindows"] == [
        {
            "limitId": "codex-spark",
            "limitName": "Codex Spark",
            "usedPercent": 12.0,
            "windowDurationMins": 1440,
            "resetsAt": 1_800_000_000,
        }
    ]


def test_normalize_snapshot_accepts_a_known_window_without_a_reset_time():
    payload = {
        "rateLimits": {
            "primary": {
                "usedPercent": 18,
                "windowDurationMins": 10080,
                "resetsAt": None,
            }
        }
    }

    snapshot = normalize_snapshot(payload, captured_at=1_799_100_000)

    assert snapshot["windows"]["weekly"] == {
        "limitId": None,
        "limitName": None,
        "usedPercent": 18.0,
        "windowDurationMins": 10080,
        "resetsAt": None,
    }
