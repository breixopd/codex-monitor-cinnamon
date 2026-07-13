"""High-level Codex Monitor operations."""

from __future__ import annotations

import time

from .models import normalize_snapshot


class CodexService:
    def __init__(self, client, history, *, remote=None, clock=time.time):
        self.client = client
        self.history = history
        self.remote = remote
        self.clock = clock

    def snapshot(self):
        captured_at = int(self.clock())
        account_response = self.client.request("account/read", {"refreshToken": False})
        limits_response = self.client.request("account/rateLimits/read")
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

    @staticmethod
    def _normalize_account(account):
        if not isinstance(account, dict):
            return None
        account_type = account.get("type")
        normalized = {"type": account_type}
        if account_type == "chatgpt":
            normalized["email"] = account.get("email")
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
