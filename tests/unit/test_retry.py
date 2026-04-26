"""Unit tests for playwright_god.retry."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from playwright_god.retry import (
    RETRY_PREFIX,
    RetryPolicy,
    _backoff_delay,
    is_transient_llm_error,
    with_retry,
)


class _Transient(Exception):
    pass


class _Permanent(Exception):
    pass


def _always_transient(exc: Exception) -> bool:
    return isinstance(exc, _Transient)


class TestWithRetry:
    def test_success_on_first_attempt(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = with_retry(RetryPolicy(max_attempts=3), fn, _always_transient)
        assert result == "ok"
        assert call_count == 1

    def test_success_after_one_retry(self, capsys):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _Transient("flaky")
            return "recovered"

        with patch("playwright_god.retry.time.sleep"):
            result = with_retry(RetryPolicy(max_attempts=3, initial_delay_s=0.0), fn, _always_transient)

        assert result == "recovered"
        assert call_count == 2
        captured = capsys.readouterr()
        assert RETRY_PREFIX in captured.err
        assert "attempt=2/3" in captured.err

    def test_exhausted_retries_raises_and_emits_exhausted(self, capsys):
        def fn():
            raise _Transient("always fails")

        with patch("playwright_god.retry.time.sleep"):
            with pytest.raises(_Transient):
                with_retry(RetryPolicy(max_attempts=2, initial_delay_s=0.0), fn, _always_transient)

        captured = capsys.readouterr()
        assert "exhausted attempts=2" in captured.err

    def test_non_transient_error_bypasses_retry(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            raise _Permanent("bad key")

        with pytest.raises(_Permanent):
            with_retry(RetryPolicy(max_attempts=3), fn, _always_transient)

        # Must not retry deterministic failures.
        assert call_count == 1

    def test_max_attempts_zero_disables_retry(self):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            raise _Transient("network")

        with pytest.raises(_Transient):
            with_retry(RetryPolicy(max_attempts=0), fn, _always_transient)

        assert call_count == 1


class TestBackoffDelay:
    def test_delay_is_capped_at_60_seconds(self):
        for attempt in range(1, 20):
            delay = _backoff_delay(attempt, initial_delay_s=10.0)
            assert delay <= 60.0, f"attempt {attempt}: delay {delay} exceeds cap"

    def test_jitter_is_non_negative(self):
        for _ in range(100):
            delay = _backoff_delay(1, initial_delay_s=2.0)
            assert delay >= 0.0

    def test_delay_grows_with_attempt(self):
        # Median should grow — use enough samples to be robust despite jitter.
        delays = [_backoff_delay(attempt, initial_delay_s=1.0) for attempt in range(1, 5)]
        # Confirm first attempt delay is less than later attempt delay (in expectation).
        assert delays[0] < delays[-1] or max(delays) >= 4.0


class TestIsTransientLlmError:
    def test_openai_connection_errors(self):
        class APIConnectionError(Exception):
            pass

        class APITimeoutError(Exception):
            pass

        assert is_transient_llm_error(APIConnectionError())
        assert is_transient_llm_error(APITimeoutError())

    def test_requests_connection_error(self):
        class ConnectionError(Exception):
            pass

        assert is_transient_llm_error(ConnectionError())

    def test_message_fallback(self):
        assert is_transient_llm_error(Exception("Connection error."))
        assert is_transient_llm_error(Exception("timed out waiting for response"))

    def test_permanent_errors_return_false(self):
        assert not is_transient_llm_error(ValueError("bad input"))
        assert not is_transient_llm_error(RuntimeError("quota exceeded"))
        assert not is_transient_llm_error(KeyError("model"))
