"""Retry decision logic and delay calculation for failed tasks."""

from __future__ import annotations

from datetime import timedelta

from computepilot.models.workflow import RetryPolicy
from computepilot.runtime.executor import TaskResult


def should_retry(result: TaskResult, policy: RetryPolicy) -> bool:
    """Return ``True`` if *result* is eligible for a retry under *policy*.

    Eligibility rules:

    * Tasks that succeeded (``result.ok is True``) are never retried.
    * Tasks whose exit code is present in *policy* and is **not** in
      ``policy.retryable_exit_codes`` are not retried.
    * All other failures are eligible (the caller must additionally check
      that the attempt count does not exceed ``policy.max_attempts``).
    """
    return not (
        result.ok
        or (result.exit_code is not None and result.exit_code not in policy.retryable_exit_codes)
    )


def next_delay(attempt: int, policy: RetryPolicy) -> timedelta:
    """Return the delay before retry *attempt* (1-indexed).

    The delay depends on ``policy.backoff``:

    * ``"none"`` — zero delay.
    * ``"fixed"`` — ``policy.base_delay``.
    * ``"exponential"`` — ``min(base_delay * 2 ** (attempt - 1), policy.max_delay)``.
    """
    if policy.backoff == "none":
        return timedelta(seconds=0)
    if policy.backoff == "fixed":
        return policy.base_delay
    # exponential
    delay: timedelta = policy.base_delay * (2 ** (attempt - 1))
    return delay if delay < policy.max_delay else policy.max_delay
