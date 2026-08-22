"""The cost controls refuse before the model is called, and roll over on their own.

A fake clock drives every test, so an hour and a day pass in no time and the windows are
exercised exactly.
"""

from __future__ import annotations

import pytest

from afterward.ask.limits import DAY, HOUR, LimitExceeded, Limits, Meter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def meter(**limits: int) -> tuple[Meter, Clock]:
    clock = Clock()
    return Meter(limits=Limits(**limits), clock=clock), clock


class TestPerClient:
    def test_window_fills_then_refuses_then_frees(self) -> None:
        m, clock = meter(client_per_hour=2)
        m.admit("a")
        m.admit("a")
        with pytest.raises(LimitExceeded) as excinfo:
            m.admit("a")
        assert excinfo.value.scope == "client_per_hour"
        assert 0 < excinfo.value.retry_after <= HOUR + 1
        m.admit("b")  # another client is unaffected
        clock.now += HOUR
        m.admit("a")  # the window has slid


class TestDaily:
    def test_request_cap(self) -> None:
        m, clock = meter(daily_requests=2, client_per_hour=100)
        m.admit("a")
        m.admit("b")
        with pytest.raises(LimitExceeded) as excinfo:
            m.admit("c")
        assert excinfo.value.scope == "daily_requests"
        assert excinfo.value.retry_after <= DAY
        clock.now += DAY
        m.admit("c")
        assert m.snapshot()["day_requests"] == 1

    def test_output_token_cap(self) -> None:
        m, _ = meter(daily_output_tokens=10, client_per_hour=100)
        m.admit("a")
        m.record_output_tokens(4)
        m.record_output_tokens(-3)  # ignored
        m.record_output_tokens(6)
        with pytest.raises(LimitExceeded) as excinfo:
            m.admit("a")
        assert excinfo.value.scope == "daily_output_tokens"
        assert m.snapshot() == {"day_requests": 1, "day_output_tokens": 10, "clients_seen": 1}


class TestLimitsFromEnv:
    def test_defaults_and_overrides_and_garbage(self) -> None:
        assert Limits.from_env({}) == Limits()
        assert Limits.from_env({"AFTERWARD_AI_CLIENT_PER_HOUR": "3"}).client_per_hour == 3
        assert (
            Limits.from_env({"AFTERWARD_AI_DAILY_REQUESTS": "x"}).daily_requests
            == Limits().daily_requests
        )
        assert (
            Limits.from_env({"AFTERWARD_AI_DAILY_OUTPUT_TOKENS": "5"}).as_dict()[
                "daily_output_tokens"
            ]
            == 5
        )
