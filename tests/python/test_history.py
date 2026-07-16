import json
import os
from pathlib import Path

from codex_bridge import history as history_module
from codex_bridge.history import MAX_HISTORY_BYTES, QuotaHistory


def _snapshot(captured_at, five_hour, weekly):
    return {
        "capturedAt": captured_at,
        "windows": {
            "fiveHour": {"usedPercent": five_hour, "resetsAt": captured_at + 300},
            "weekly": {"usedPercent": weekly, "resetsAt": captured_at + 600},
        },
    }


def _history_row(captured_at, five_hour=10, weekly=20):
    return {
        "capturedAt": captured_at,
        "fiveHourUsedPercent": five_hour,
        "fiveHourResetsAt": captured_at + 300,
        "weeklyUsedPercent": weekly,
        "weeklyResetsAt": captured_at + 600,
    }


def _write_rows(path, rows):
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    )


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
    path = tmp_path / "history.jsonl"
    history = QuotaHistory(path, retention_days=30)

    history.append(_snapshot(100, 10, 20), now=100)
    history.append(_snapshot(250, 11, 21), now=250)
    history.append(_snapshot(401, 12, 22), now=401)

    rows = history.load(now=401)
    persisted = [json.loads(line) for line in path.read_text().splitlines()]

    assert [row["capturedAt"] for row in rows] == [250, 401]
    assert rows[0]["fiveHourUsedPercent"] == 11.0
    assert [row["capturedAt"] for row in persisted] == [100, 250, 401]


def test_history_appends_new_buckets_without_rewriting_the_log(tmp_path):
    path = tmp_path / "history.jsonl"
    history = QuotaHistory(path, retention_days=30)

    history.append(_snapshot(100, 10, 20), now=100)
    original_inode = path.stat().st_ino
    original_payload = path.read_bytes()
    history.append(_snapshot(401, 12, 22), now=401)

    assert path.stat().st_ino == original_inode
    assert path.read_bytes().startswith(original_payload)
    assert len(path.read_text().splitlines()) == 2
    assert path.stat().st_mode & 0o777 == 0o600


def test_history_compacts_periodically_instead_of_on_every_append(
    tmp_path, monkeypatch
):
    history = QuotaHistory(tmp_path / "history.jsonl", retention_days=30)
    writes = []
    original_write = history._write

    def record_write(rows):
        writes.append(rows)
        original_write(rows)

    monkeypatch.setattr(history, "_write", record_write)

    history.append(_snapshot(100, 10, 20), now=100)
    history.append(_snapshot(250, 11, 21), now=250)
    history.append(_snapshot(86_501, 12, 22), now=86_501)

    assert len(writes) == 1
    assert [row["capturedAt"] for row in history.load(now=86_501)] == [250, 86_501]


def test_history_rejects_oversized_files_without_reading_them(tmp_path):
    path = tmp_path / "history.jsonl"
    with path.open("wb") as handle:
        handle.truncate(MAX_HISTORY_BYTES + 1)

    assert QuotaHistory(path, retention_days=30).load(now=100) == []


def test_history_recovers_oversized_files_without_reading_them(
    tmp_path, monkeypatch
):
    path = tmp_path / "history.jsonl"
    with path.open("wb") as handle:
        handle.truncate(MAX_HISTORY_BYTES + 1)
    original_open = Path.open

    def reject_payload_read(self, *args, **kwargs):
        if self == path and args and args[0] == "rb":
            raise AssertionError("oversized history payload must not be read")
        return original_open(self, *args, **kwargs)

    history = QuotaHistory(path, retention_days=30)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", reject_payload_read)
        history.append(_snapshot(100, 10, 20), now=100)

    assert path.stat().st_size < MAX_HISTORY_BYTES
    assert path.stat().st_mode & 0o777 == 0o600
    assert [row["capturedAt"] for row in history.load(now=100)] == [100]


def test_compaction_keeps_newest_complete_rows_within_the_hard_cap(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(history_module, "MAX_HISTORY_BYTES", 280)
    path = tmp_path / "history.jsonl"
    history = QuotaHistory(path, retention_days=365)

    history.append(_snapshot(100, 10, 20), now=100)
    history.append(_snapshot(401, 11, 21), now=401)
    history.append(_snapshot(701, 12, 22), now=701)

    assert path.stat().st_size <= 280
    assert history.load(now=701)[-1]["capturedAt"] == 701


def test_history_skips_individual_lines_with_invalid_encoding(tmp_path):
    path = tmp_path / "history.jsonl"
    valid = {
        "capturedAt": 100,
        "fiveHourUsedPercent": 10,
        "fiveHourResetsAt": 400,
        "weeklyUsedPercent": 20,
        "weeklyResetsAt": 700,
    }
    path.write_bytes(b"\xff\xfe\n" + json.dumps(valid).encode() + b"\n")

    assert QuotaHistory(path, retention_days=30).load(now=100) == [valid]


def test_display_window_does_not_delete_older_retained_rows(tmp_path):
    path = tmp_path / "history.jsonl"
    now = 10_000_000
    old = now - 45 * 86_400
    recent = now - 10 * 86_400
    history = QuotaHistory(path, retention_days=90)

    history.append(_snapshot(old, 10, 20), now=old)
    history.append(_snapshot(recent, 30, 40), now=recent)

    assert [row["capturedAt"] for row in history.load(now=now)] == [old, recent]
    assert [
        row["capturedAt"]
        for row in history.load_for_display(now=now, days=30)
    ] == [recent]
    assert [
        json.loads(line)["capturedAt"] for line in path.read_text().splitlines()
    ] == [old, recent]


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
        "_append_line",
        lambda _line: (_ for _ in ()).throw(OSError("disk full")),
    )
    history.append(_snapshot(100, 10, 20), now=100)


def test_history_reuses_normalized_cache_without_reopening_unchanged_file(
    tmp_path, monkeypatch
):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100)])
    history = QuotaHistory(path, retention_days=30)

    assert history.load(now=100)[0]["capturedAt"] == 100
    original_open = Path.open

    def reject_payload_read(self, *args, **kwargs):
        if self == path and args and args[0] == "rb":
            raise AssertionError("unchanged history must use its normalized cache")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_payload_read)

    assert history.load_for_display(now=101, days=30)[0]["capturedAt"] == 100


def test_warm_cache_tracks_bucket_replacement_and_new_append_without_reparse(
    tmp_path, monkeypatch
):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100), _history_row(401)])
    history = QuotaHistory(path, retention_days=30)
    history.load(now=401)

    monkeypatch.setattr(
        history_module.json,
        "loads",
        lambda _payload: (_ for _ in ()).throw(
            AssertionError("warm append+load must not reparse JSON")
        ),
    )

    history.append(_snapshot(250, 11, 21), now=401)
    history.append(_snapshot(701, 12, 22), now=701)

    rows = history.load_for_display(now=701, days=30)
    assert [row["capturedAt"] for row in rows] == [250, 401, 701]
    assert rows[0]["fiveHourUsedPercent"] == 11.0


def test_history_cache_detects_external_atomic_replacement(tmp_path):
    path = tmp_path / "history.jsonl"
    replacement = tmp_path / "replacement.jsonl"
    _write_rows(path, [_history_row(100)])
    history = QuotaHistory(path, retention_days=30)
    history.load(now=100)

    _write_rows(replacement, [_history_row(401, five_hour=30)])
    replacement.replace(path)

    rows = history.load(now=401)
    assert [row["capturedAt"] for row in rows] == [401]
    assert rows[0]["fiveHourUsedPercent"] == 30.0


def test_external_in_place_change_before_append_invalidates_warm_cache(tmp_path):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100)])
    history = QuotaHistory(path, retention_days=30)
    history.load(now=100)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_history_row(401), separators=(",", ":")) + "\n")
    history.append(_snapshot(701, 30, 40), now=701)

    assert [row["capturedAt"] for row in history.load(now=701)] == [100, 401, 701]


def test_append_after_external_deletion_does_not_restore_stale_cached_rows(tmp_path):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100)])
    history = QuotaHistory(path, retention_days=30)
    history.load(now=100)

    path.unlink()
    history.append(_snapshot(701, 30, 40), now=701)

    assert [row["capturedAt"] for row in history.load(now=701)] == [701]


def test_history_cache_detects_same_size_rewrite_with_restored_mtime(tmp_path):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100, five_hour=10)])
    history = QuotaHistory(path, retention_days=30)
    history.load(now=100)
    original_stat = path.stat()
    original_size = original_stat.st_size

    _write_rows(path, [_history_row(100, five_hour=30)])
    os.utime(
        path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    assert path.stat().st_size == original_size
    assert history.load(now=100)[0]["fiveHourUsedPercent"] == 30.0


def test_cached_future_row_becomes_visible_as_time_advances_without_reparse(
    tmp_path, monkeypatch
):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100), _history_row(401)])
    history = QuotaHistory(path, retention_days=30)

    assert [row["capturedAt"] for row in history.load(now=100)] == [100]
    original_open = Path.open

    def reject_payload_read(self, *args, **kwargs):
        if self == path and args and args[0] == "rb":
            raise AssertionError("time-window filtering must reuse normalized rows")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_payload_read)

    assert [row["capturedAt"] for row in history.load(now=101)] == [100, 401]


def test_cached_rows_are_isolated_from_caller_mutation(tmp_path):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100)])
    history = QuotaHistory(path, retention_days=30)

    rows = history.load(now=100)
    rows[0]["fiveHourUsedPercent"] = 99

    assert history.load(now=100)[0]["fiveHourUsedPercent"] == 10.0


def test_oversized_external_change_invalidates_warm_cache(tmp_path):
    path = tmp_path / "history.jsonl"
    _write_rows(path, [_history_row(100)])
    history = QuotaHistory(path, retention_days=30)
    assert history.load(now=100)

    with path.open("wb") as handle:
        handle.truncate(MAX_HISTORY_BYTES + 1)

    assert history.load(now=100) == []
