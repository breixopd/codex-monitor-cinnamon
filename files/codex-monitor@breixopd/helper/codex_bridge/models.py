"""Normalize Codex app-server payloads for the Cinnamon UI."""

from __future__ import annotations

from typing import Any


FIVE_HOUR_MINUTES = 300
WEEKLY_MINUTES = 10_080


def _normalize_window(
    window: dict[str, Any], *, limit_id: str | None, limit_name: str | None
) -> dict[str, Any]:
    used_percent = max(0.0, min(100.0, float(window.get("usedPercent", 0))))
    return {
        "limitId": limit_id,
        "limitName": limit_name,
        "usedPercent": used_percent,
        "windowDurationMins": int(window["windowDurationMins"]),
        "resetsAt": int(window["resetsAt"]),
    }


def _normalize_reset_credits(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"availableCount": 0, "credits": []}

    credits = []
    for raw in value.get("credits") or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            continue
        credits.append(
            {
                "id": raw["id"],
                "resetType": raw.get("resetType", "unknown"),
                "status": raw.get("status", "unknown"),
                "grantedAt": int(raw["grantedAt"]),
                "expiresAt": (
                    int(raw["expiresAt"])
                    if raw.get("expiresAt") is not None
                    else None
                ),
                "title": raw.get("title"),
                "description": raw.get("description"),
            }
        )
    return {"availableCount": int(value.get("availableCount", 0)), "credits": credits}


def normalize_snapshot(payload: dict[str, Any], *, captured_at: int) -> dict[str, Any]:
    """Return a UI-safe snapshot from an account/rateLimits/read response."""
    base = payload.get("rateLimits") or {}
    buckets_by_id = payload.get("rateLimitsByLimitId")
    buckets = list(buckets_by_id.values()) if isinstance(buckets_by_id, dict) else [base]
    if not buckets:
        buckets = [base]

    windows: dict[str, dict[str, Any] | None] = {"fiveHour": None, "weekly": None}
    extra_windows: list[dict[str, Any]] = []

    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        limit_id = bucket.get("limitId")
        limit_name = bucket.get("limitName")
        for key in ("primary", "secondary"):
            raw_window = bucket.get(key)
            if not isinstance(raw_window, dict):
                continue
            normalized = _normalize_window(
                raw_window, limit_id=limit_id, limit_name=limit_name
            )
            duration = normalized["windowDurationMins"]
            if duration == FIVE_HOUR_MINUTES and windows["fiveHour"] is None:
                windows["fiveHour"] = normalized
            elif duration == WEEKLY_MINUTES and windows["weekly"] is None:
                windows["weekly"] = normalized
            else:
                extra_windows.append(normalized)

    return {
        "capturedAt": int(captured_at),
        "planType": base.get("planType"),
        "windows": windows,
        "extraWindows": extra_windows,
        "credits": base.get("credits"),
        "individualLimit": base.get("individualLimit"),
        "rateLimitReachedType": base.get("rateLimitReachedType"),
        "resetCredits": _normalize_reset_credits(payload.get("rateLimitResetCredits")),
    }
