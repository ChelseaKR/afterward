"""Cost controls: a per-client rate limit and a hard daily cap, in memory, fail-closed.

Both are counted per process. A deployment with more than one process multiplies the cap by
the process count, which is why the prepared Lambda shape also sets reserved concurrency and
a budget alarm (``infra/``). A limit that is hit returns 429 to the page, and the page keeps
working without the panel; nothing deterministic depends on this service.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

CLIENT_PER_HOUR_ENV = "AFTERWARD_AI_CLIENT_PER_HOUR"
DAILY_REQUESTS_ENV = "AFTERWARD_AI_DAILY_REQUESTS"
DAILY_OUTPUT_TOKENS_ENV = "AFTERWARD_AI_DAILY_OUTPUT_TOKENS"

DEFAULT_CLIENT_PER_HOUR = 20
DEFAULT_DAILY_REQUESTS = 400
DEFAULT_DAILY_OUTPUT_TOKENS = 400_000
"""Roughly 400 narrations a day. At Sonnet list prices that is a few dollars, not a bill."""

HOUR = 3600.0
DAY = 86400.0


class LimitExceeded(Exception):
    def __init__(self, scope: str, retry_after: int) -> None:
        super().__init__(f"{scope} limit reached")
        self.scope = scope
        self.retry_after = retry_after


@dataclass
class Limits:
    client_per_hour: int = DEFAULT_CLIENT_PER_HOUR
    daily_requests: int = DEFAULT_DAILY_REQUESTS
    daily_output_tokens: int = DEFAULT_DAILY_OUTPUT_TOKENS

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Limits:
        env = os.environ if environ is None else environ
        return cls(
            client_per_hour=_int(env.get(CLIENT_PER_HOUR_ENV), DEFAULT_CLIENT_PER_HOUR),
            daily_requests=_int(env.get(DAILY_REQUESTS_ENV), DEFAULT_DAILY_REQUESTS),
            daily_output_tokens=_int(env.get(DAILY_OUTPUT_TOKENS_ENV), DEFAULT_DAILY_OUTPUT_TOKENS),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "client_per_hour": self.client_per_hour,
            "daily_requests": self.daily_requests,
            "daily_output_tokens": self.daily_output_tokens,
        }


def _int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass
class Meter:
    """Counts requests per client over an hour and requests and tokens per day overall."""

    limits: Limits = field(default_factory=Limits)
    clock: object = time.monotonic
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _clients: dict[str, deque[float]] = field(default_factory=dict, repr=False)
    _day_started: float | None = None
    _day_requests: int = 0
    _day_output_tokens: int = 0

    def _now(self) -> float:
        now: float = self.clock()  # type: ignore[operator]
        return now

    def admit(self, client_key: str) -> None:
        """Raise :class:`LimitExceeded` if this request may not proceed; otherwise count it."""
        now = self._now()
        with self._lock:
            self._roll_day(now)
            if self._day_requests >= self.limits.daily_requests:
                raise LimitExceeded("daily_requests", self._seconds_to_day_end(now))
            if self._day_output_tokens >= self.limits.daily_output_tokens:
                raise LimitExceeded("daily_output_tokens", self._seconds_to_day_end(now))
            window = self._clients.setdefault(client_key, deque())
            while window and now - window[0] >= HOUR:
                window.popleft()
            if len(window) >= self.limits.client_per_hour:
                raise LimitExceeded("client_per_hour", int(HOUR - (now - window[0])) + 1)
            window.append(now)
            self._day_requests += 1

    def record_output_tokens(self, count: int) -> None:
        with self._lock:
            self._day_output_tokens += max(0, count)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "day_requests": self._day_requests,
                "day_output_tokens": self._day_output_tokens,
                "clients_seen": len(self._clients),
            }

    def _roll_day(self, now: float) -> None:
        if self._day_started is None or now - self._day_started >= DAY:
            self._day_started = now
            self._day_requests = 0
            self._day_output_tokens = 0
            self._clients.clear()

    def _seconds_to_day_end(self, now: float) -> int:
        started = self._day_started if self._day_started is not None else now
        return max(1, int(DAY - (now - started)))
