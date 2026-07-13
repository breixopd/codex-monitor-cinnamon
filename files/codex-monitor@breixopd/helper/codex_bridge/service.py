"""High-level Codex Monitor operations."""

from __future__ import annotations

import copy
import time

from .models import normalize_snapshot
from .sessions import normalize_session_list


class CodexService:
    def __init__(self, client, history, *, remote=None, launcher=None, clock=time.time):
        self.client = client
        self.history = history
        self.remote = remote
        self.launcher = launcher
        self.clock = clock
        self._notification_probe_complete = False

    def snapshot(self):
        captured_at = int(self.clock())
        account_response = self.client.request("account/read", {"refreshToken": False})
        limits_response = self.client.request("account/rateLimits/read")
        limits_response = self._merge_latest_rate_limits(limits_response)
        snapshot = normalize_snapshot(limits_response, captured_at=captured_at)
        snapshot["account"] = self._normalize_account(account_response.get("account"))

        token_usage = None
        activity_available = True
        try:
            token_usage = self._normalize_token_usage(
                self.client.request("account/usage/read")
            )
        except RuntimeError as error:
            if "(-32601)" not in str(error):
                raise
            activity_available = False

        snapshot["tokenUsage"] = token_usage
        snapshot["capabilities"] = {
            "activity": activity_available,
            "resetCredits": "rateLimitResetCredits" in limits_response,
        }
        if self.history is not None:
            self.history.append(snapshot, now=captured_at)
            snapshot["history"] = self.history.load(now=captured_at)
        else:
            snapshot["history"] = []
        return snapshot

    def consume_reset(self, credit_id, idempotency_key):
        return self.client.request(
            "account/rateLimitResetCredit/consume",
            {"creditId": credit_id, "idempotencyKey": idempotency_key},
        )

    def sessions(self, limit=12):
        response = self.client.request(
            "thread/list",
            {"limit": limit, "sortKey": "updated_at", "sortDirection": "desc"},
        )
        return normalize_session_list(response, limit=limit)

    def open_codex(self):
        return self._require_launcher().open_codex()

    def open_session(self, thread_id, cwd=None):
        return self._require_launcher().open_session(thread_id, cwd)

    def remote_status(self):
        return self._require_remote().status()

    def remote_start(self):
        return self._require_remote().start()

    def remote_stop(self):
        return self._require_remote().stop()

    def remote_pair(self):
        return self._require_remote().pair()

    def _require_remote(self):
        if self.remote is None:
            raise RuntimeError("Codex remote control is unavailable")
        return self.remote

    def _require_launcher(self):
        if self.launcher is None:
            raise RuntimeError("Codex terminal launcher is unavailable")
        return self.launcher

    def _merge_latest_rate_limits(self, response):
        wait = getattr(self.client, "wait_for_notification", None)
        if wait is None:
            return response
        timeout = 0 if self._notification_probe_complete else 1.0
        self._notification_probe_complete = True
        params = wait("account/rateLimits/updated", timeout_seconds=timeout)
        update = params.get("rateLimits") if isinstance(params, dict) else None
        if not isinstance(update, dict):
            return response

        merged = copy.deepcopy(response)
        merged["rateLimits"] = self._merge_non_null(
            merged.get("rateLimits"), update
        )
        buckets = merged.get("rateLimitsByLimitId")
        update_id = update.get("limitId")
        if isinstance(buckets, dict) and isinstance(update_id, str):
            for key, bucket in buckets.items():
                if key == update_id or (
                    isinstance(bucket, dict) and bucket.get("limitId") == update_id
                ):
                    buckets[key] = self._merge_non_null(bucket, update)
        return merged

    @classmethod
    def _merge_non_null(cls, base, update):
        result = copy.deepcopy(base) if isinstance(base, dict) else {}
        for key, value in update.items():
            if value is None:
                continue
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = cls._merge_non_null(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    @staticmethod
    def _normalize_account(account):
        if not isinstance(account, dict):
            return None
        account_type = account.get("type")
        normalized = {"type": account_type}
        if account_type == "chatgpt":
            normalized["planType"] = account.get("planType")
        return normalized

    @staticmethod
    def _normalize_token_usage(value):
        if not isinstance(value, dict):
            return None
        summary = value.get("summary") if isinstance(value.get("summary"), dict) else {}
        buckets = []
        for raw in value.get("dailyUsageBuckets") or []:
            if not isinstance(raw, dict):
                continue
            buckets.append(
                {"startDate": str(raw["startDate"]), "tokens": int(raw["tokens"])}
            )
        return {
            "summary": {
                key: (int(item) if item is not None else None)
                for key, item in summary.items()
            },
            "dailyUsageBuckets": buckets,
        }
