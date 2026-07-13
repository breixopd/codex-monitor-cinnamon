"""Local quota-history persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SECONDS_PER_DAY = 86_400
REQUIRED_KEYS = {
    "capturedAt",
    "fiveHourUsedPercent",
    "fiveHourResetsAt",
    "weeklyUsedPercent",
    "weeklyResetsAt",
}


class QuotaHistory:
    def __init__(self, path, *, retention_days):
        self.path = Path(path)
        self.retention_days = max(1, int(retention_days))

    def append(self, snapshot, *, now):
        rows = self.load(now=now)
        sample = self._to_sample(snapshot)
        if sample is not None:
            rows.append(sample)
        self._write(rows)

    def load(self, *, now):
        cutoff = int(now) - self.retention_days * SECONDS_PER_DAY
        rows: list[dict[str, Any]] = []
        if not self.path.exists():
            return rows
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return rows
        for line in lines:
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(row, dict) or not REQUIRED_KEYS.issubset(row):
                continue
            if int(row["capturedAt"]) < cutoff:
                continue
            rows.append(row)
        return rows

    @staticmethod
    def _to_sample(snapshot):
        windows = snapshot.get("windows") or {}
        five_hour = windows.get("fiveHour")
        weekly = windows.get("weekly")
        if not isinstance(five_hour, dict) or not isinstance(weekly, dict):
            return None
        return {
            "capturedAt": int(snapshot["capturedAt"]),
            "fiveHourUsedPercent": float(five_hour["usedPercent"]),
            "fiveHourResetsAt": int(five_hour["resetsAt"]),
            "weeklyUsedPercent": float(weekly["usedPercent"]),
            "weeklyResetsAt": int(weekly["resetsAt"]),
        }

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, self.path)
