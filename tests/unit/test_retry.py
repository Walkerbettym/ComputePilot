"""Unit tests for retry decision logic and delay calculation."""

from __future__ import annotations

from datetime import timedelta

from computepilot.models.workflow import RetryPolicy
from computepilot.runtime.executor import TaskResult
from computepilot.runtime.retry import next_delay, should_retry


class TestShouldRetry:
    """Tests for ``should_retry()``."""

    def test_success_not_retried(self) -> None:
        result = TaskResult(task_id="t1", ok=True, exit_code=0)
        policy = RetryPolicy(max_attempts=3)
        assert should_retry(result, policy) is False

    def test_failure_with_retryable_code(self) -> None:
        result = TaskResult(task_id="t1", ok=False, exit_code=137)
        policy = RetryPolicy(max_attempts=3, retryable_exit_codes=[1, 2, 137])
        assert should_retry(result, policy) is True

    def test_failure_with_non_retryable_code(self) -> None:
        result = TaskResult(task_id="t1", ok=False, exit_code=3)
        policy = RetryPolicy(max_attempts=3, retryable_exit_codes=[1, 2, 137])
        assert should_retry(result, policy) is False

    def test_failure_no_exit_code(self) -> None:
        result = TaskResult(task_id="t1", ok=False, exit_code=None)
        policy = RetryPolicy(max_attempts=3)
        assert should_retry(result, policy) is True

    def test_empty_retryable_codes(self) -> None:
        result = TaskResult(task_id="t1", ok=False, exit_code=1)
        policy = RetryPolicy(max_attempts=3, retryable_exit_codes=[])
        assert should_retry(result, policy) is False

    def test_default_policy_retries_exit_1(self) -> None:
        result = TaskResult(task_id="t1", ok=False, exit_code=1)
        policy = RetryPolicy()
        assert should_retry(result, policy) is True


class TestNextDelay:
    """Tests for ``next_delay()``."""

    def test_backoff_none(self) -> None:
        policy = RetryPolicy(backoff="none")
        assert next_delay(1, policy) == timedelta(seconds=0)
        assert next_delay(5, policy) == timedelta(seconds=0)

    def test_backoff_fixed(self) -> None:
        policy = RetryPolicy(backoff="fixed", base_delay=timedelta(seconds=10))
        assert next_delay(1, policy) == timedelta(seconds=10)
        assert next_delay(3, policy) == timedelta(seconds=10)

    def test_backoff_exponential(self) -> None:
        policy = RetryPolicy(
            backoff="exponential",
            base_delay=timedelta(seconds=5),
            max_delay=timedelta(seconds=300),
        )
        # 5 * 2^(1-1) = 5
        assert next_delay(1, policy) == timedelta(seconds=5)
        # 5 * 2^(2-1) = 10
        assert next_delay(2, policy) == timedelta(seconds=10)
        # 5 * 2^(3-1) = 20
        assert next_delay(3, policy) == timedelta(seconds=20)

    def test_exponential_capped_at_max_delay(self) -> None:
        policy = RetryPolicy(
            backoff="exponential",
            base_delay=timedelta(seconds=10),
            max_delay=timedelta(seconds=30),
        )
        # 10 * 2^(2-1) = 20
        assert next_delay(2, policy) == timedelta(seconds=20)
        # 10 * 2^(3-1) = 40, capped at 30
        assert next_delay(3, policy) == timedelta(seconds=30)
        # Large attempt — still capped at 30
        assert next_delay(10, policy) == timedelta(seconds=30)
