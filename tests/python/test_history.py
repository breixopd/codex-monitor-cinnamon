import json

from codex_bridge.history import QuotaHistory


def _snapshot(captured_at, five_hour, weekly):
    return {
        "capturedAt": captured_at,
        "windows": {
            "fiveHour": {"usedPercent": five_hour, "resetsAt": captured_at + 300},
            "weekly": {"usedPercent": weekly, "resetsAt": captured_at + 600},
        },
    }


def test_history_appends_minimal_samples_and_prunes_expired_rows(tmp_path):
    path = tmp_path / "history.jsonl"
    history = QuotaHistory(path, retention_days=1)

    history.append(_snapshot(100, 10, 20), now=100)
    history.append(_snapshot(90_000, 30, 40), now=90_000)

    rows = history.load(now=90_000)
    persisted = [json.loads(line) for line in path.read_text().splitlines()]

    assert rows == [
        {
            "capturedAt": 90_000,
            "fiveHourUsedPercent": 30.0,
            "fiveHourResetsAt": 90_300,
            "weeklyUsedPercent": 40.0,
            "weeklyResetsAt": 90_600,
        }
    ]
    assert persisted == rows


def test_history_ignores_corrupt_and_incomplete_rows(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text('{"capturedAt": 50}\nnot-json\n')

    rows = QuotaHistory(path, retention_days=30).load(now=100)

    assert rows == []
