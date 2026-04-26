"""Exponential-backoff retry for transient LLM provider failures.

Usage::

    policy = RetryPolicy(max_attempts=3, initial_delay_s=2.0)
    result = with_retry(policy, lambda: llm_client.complete(prompt), is_transient)

The caller is responsible for defining ``is_transient`` — a predicate that
returns ``True`` for exceptions that are safe to retry (e.g. network timeouts)
and ``False`` for deterministic failures (bad API key, quota, etc.).
"""

from __future__ import annotations

import random
import sys
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

RETRY_PREFIX = "[pg:retry]"

T = TypeVar("T")


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_s: float = 2.0


def with_retry(
    policy: RetryPolicy,
    fn: Callable[[], T],
    is_transient: Callable[[Exception], bool],
) -> T:
    """Call ``fn`` up to ``policy.max_attempts`` times.

    On a transient exception, emit a ``[pg:retry]`` line to stderr and wait
    for an exponentially-increasing delay with full jitter before retrying.
    Non-transient exceptions propagate immediately without any retry.

    Raises the last exception when all attempts are exhausted.
    """
    if policy.max_attempts <= 0:
        # Retries disabled — invoke once and propagate any error.
        return fn()

    last_exc: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc) or attempt >= policy.max_attempts:
                if attempt >= policy.max_attempts and is_transient(exc):
                    print(
                        f"{RETRY_PREFIX} exhausted attempts={policy.max_attempts}",
                        file=sys.stderr,
                        flush=True,
                    )
                raise
            last_exc = exc
            delay = _backoff_delay(attempt, policy.initial_delay_s)
            print(
                f"{RETRY_PREFIX} attempt={attempt + 1}/{policy.max_attempts} delay={delay:.1f}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)

    # Should never be reached — kept for type checker.
    if last_exc is not None:
        raise last_exc
    return fn()  # pragma: no cover


def _backoff_delay(attempt: int, initial_delay_s: float) -> float:
    """Exponential backoff with full jitter, capped at 60 s.

    Formula: min(initial * 2^(attempt-1) + uniform(0, initial), 60)
    """
    base = initial_delay_s * (2 ** (attempt - 1))
    jitter = random.uniform(0, initial_delay_s)
    return min(base + jitter, 60.0)


def is_transient_llm_error(exc: Exception) -> bool:
    """Return True for network/connectivity exceptions from any supported provider."""
    cls_name = exc.__class__.__name__
    # OpenAI SDK transient errors
    if cls_name in ("APIConnectionError", "APITimeoutError"):
        return True
    # Anthropic / httpx transient errors
    if cls_name in ("ConnectError", "ConnectTimeout", "ReadTimeout", "RemoteProtocolError"):
        return True
    # requests (OllamaClient) transient errors
    if cls_name in ("ConnectionError", "Timeout", "ReadTimeout"):
        return True
    # Generic fallback: check the message for connection indicators
    msg = str(exc).lower()
    if any(tok in msg for tok in ("connection error", "connection refused", "timed out", "network", "dns")):
        return True
    return False
