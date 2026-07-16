import json

from codex_bridge.history import MAX_HISTORY_BYTES, QuotaHistory


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
    path.write_text(
        '{"capturedAt": 50}\nnot-json\n'
        '{"capturedAt":"invalid","fiveHourUsedPercent":null,'
        '"fiveHourResetsAt":null,"weeklyUsedPercent":20,'
        '"weeklyResetsAt":700}\n'
    )

    rows = QuotaHistory(path, retention_days=30).load(now=100)

    assert rows == []


def test_history_persists_a_snapshot_when_only_one_quota_window_is_available(tmp_path):
    path = tmp_path / "history.jsonl"
    history = QuotaHistory(path, retention_days=30)
    snapshot = {
        "capturedAt": 100,
        "windows": {
            "fiveHour": None,
            "weekly": {"usedPercent": 42, "resetsAt": 700},
        },
    }

    history.append(snapshot, now=100)

    assert history.load(now=100) == [
        {
            "capturedAt": 100,
            "fiveHourUsedPercent": None,
            "fiveHourResetsAt": None,
            "weeklyUsedPercent": 42.0,
            "weeklyResetsAt": 700,
        }
    ]


def test_history_keeps_usage_when_the_reset_time_is_unknown(tmp_path):
    history = QuotaHistory(tmp_path / "history.jsonl", retention_days=30)
    snapshot = {
        "capturedAt": 100,
        "windows": {
            "fiveHour": None,
            "weekly": {"usedPercent": 18, "resetsAt": None},
        },
    }

    history.append(snapshot, now=100)

    assert history.load(now=100)[0]["weeklyUsedPercent"] == 18.0
    assert history.load(now=100)[0]["weeklyResetsAt"] is None


def test_history_coalesces_samples_inside_five_minute_bucket(tmp_path):
    history = QuotaHistory(tmp_path / "history.jsonl", retention_days=30)

    history.append(_snapshot(100, 10, 20), now=100)
    history.append(_snapshot(250, 11, 21), now=250)
    history.append(_snapshot(401, 12, 22), now=401)

    rows = history.load(now=401)

    assert [row["capturedAt"] for row in rows] == [250, 401]
    assert rows[0]["fiveHourUsedPercent"] == 11.0


def test_history_rejects_oversized_files_without_reading_them(tmp_path):
    path = tmp_path / "history.jsonl"
    with path.open("wb") as handle:
        handle.truncate(MAX_HISTORY_BYTES + 1)

    assert QuotaHistory(path, retention_days=30).load(now=100) == []


def test_history_rejects_future_nonfinite_and_out_of_range_samples(tmp_path):
    path = tmp_path / "history.jsonl"
    valid = {
        "capturedAt": 100,
        "fiveHourUsedPercent": 10,
        "fiveHourResetsAt": 400,
        "weeklyUsedPercent": 20,
        "weeklyResetsAt": 700,
    }
    rows = [
        {**valid, "capturedAt": 401},
        {**valid, "capturedAt": 101, "fiveHourUsedPercent": float("nan")},
        {**valid, "capturedAt": 102, "weeklyUsedPercent": 101},
        {**valid, "capturedAt": 103, "weeklyResetsAt": 10**20},
        valid,
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    assert QuotaHistory(path, retention_days=30).load(now=100) == [valid]


def test_history_rejects_invalid_encoding_and_persistence_failures_are_nonfatal(
    tmp_path, monkeypatch
):
    path = tmp_path / "history.jsonl"
    path.write_bytes(b"\xff\xfe")
    history = QuotaHistory(path, retention_days=30)

    assert history.load(now=100) == []

    monkeypatch.setattr(
        history,
        "_write",
        lambda _rows: (_ for _ in ()).throw(OSError("disk full")),
    )
    history.append(_snapshot(100, 10, 20), now=100)
