from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class _CacheEntry:
    value: object
    expires_at: float


class CachedComposerCapabilitiesService:
    def __init__(
        self,
        base_service,
        ttl_seconds: int = 24 * 60 * 60,
        time_func: Callable[[], float] | None = None,
    ):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than 0.")

        self._base_service = base_service
        self._ttl_seconds = int(ttl_seconds)
        self._time_func = time_func or time.monotonic
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], _CacheEntry] = {}

    @staticmethod
    def _normalize_key(target_type: str, subreddit: str | None) -> tuple[str, str]:
        clean_target = (target_type or "").strip().lower()

        if clean_target == "profile":
            return "profile", ""

        clean_subreddit = (subreddit or "").strip().lower()
        return clean_target, clean_subreddit

    def inspect(self, target_type: str, subreddit: str | None = None):
        cache_key = self._normalize_key(target_type, subreddit)
        now = self._time_func()

        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is not None and entry.expires_at > now:
                return entry.value
            if entry is not None:
                del self._cache[cache_key]

        value = self._base_service.inspect(target_type=target_type, subreddit=subreddit)

        expires_at = self._time_func() + self._ttl_seconds
        with self._lock:
            self._cache[cache_key] = _CacheEntry(value=value, expires_at=expires_at)

        return value
