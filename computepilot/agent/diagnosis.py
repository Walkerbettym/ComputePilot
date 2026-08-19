"""Failure diagnosis: classify failures and suggest repairs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from computepilot.runtime.executor import RepairSpec


@dataclass
class Diagnosis:
    """Result of diagnosing a failed task."""

    task_id: str
    cause: str  # OOM|TIMEOUT|MISSING_INPUT|SYNTAX_ERROR|NODE_FAIL|UNKNOWN
    confidence: float
    explanation: str
    suggested_action: str  # retry|repair|human|abort
    repair: RepairSpec | None = None


OOM_PATTERNS = [
    re.compile(r"killed", re.IGNORECASE),
    re.compile(r"out of memory", re.IGNORECASE),
    re.compile(r"oom", re.IGNORECASE),
    re.compile(r"cannot allocate memory", re.IGNORECASE),
    re.compile(r"memory allocation", re.IGNORECASE),
]

TIMEOUT_PATTERNS = [
    re.compile(r"timed?\s?out", re.IGNORECASE),
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"DUE TO TIME", re.IGNORECASE),
    re.compile(r"walltime", re.IGNORECASE),
    re.compile(r"exceeded.*time", re.IGNORECASE),
]

MISSING_INPUT_PATTERNS = [
    re.compile(r"no such file", re.IGNORECASE),
    re.compile(r"file not found", re.IGNORECASE),
    re.compile(r"cannot find", re.IGNORECASE),
    re.compile(r"not found", re.IGNORECASE),
]

SYNTAX_ERROR_PATTERNS = [
    re.compile(r"SyntaxError", re.IGNORECASE),
    re.compile(r"NameError", re.IGNORECASE),
    re.compile(r"ImportError", re.IGNORECASE),
    re.compile(r"ModuleNotFoundError", re.IGNORECASE),
    re.compile(r"invalid syntax", re.IGNORECASE),
    re.compile(r"command not found", re.IGNORECASE),
]

NODE_FAIL_PATTERNS = [
    re.compile(r"node fail", re.IGNORECASE),
    re.compile(r"nodedown", re.IGNORECASE),
    re.compile(r"down: node", re.IGNORECASE),
    re.compile(r"couldn't connect", re.IGNORECASE),
    re.compile(r"connection refused", re.IGNORECASE),
    re.compile(r"network error", re.IGNORECASE),
    re.compile(r"broken pipe", re.IGNORECASE),
]


class Diagnoser:
    """Classify task failures by exit code and stderr content."""

    def diagnose(
        self,
        task_id: str,
        exit_code: int | None,
        stderr: str = "",
    ) -> Diagnosis:
        """Classify the failure and return a Diagnosis with suggested repair."""
        cause: str
        confidence: float
        explanation: str
        suggested_action: str
        repair: RepairSpec | None

        # Exit code 137 = SIGKILL (OOM killer)
        if exit_code == 137 or self._matches_any(stderr, OOM_PATTERNS):
            cause = "OOM"
            confidence = 0.9 if exit_code == 137 else 0.8
            explanation = self._build_explanation(task_id, exit_code, stderr, "OOM")
            suggested_action = "repair"
            repair = RepairSpec(action="increase_memory", params={"factor": 2.0})

        # Timeout-based
        elif self._matches_any(stderr, TIMEOUT_PATTERNS):
            cause = "TIMEOUT"
            confidence = 0.85
            explanation = self._build_explanation(task_id, exit_code, stderr, "TIMEOUT")
            suggested_action = "repair"
            repair = RepairSpec(action="increase_walltime", params={"factor": 1.5})

        # Syntax / code error
        elif self._matches_any(stderr, SYNTAX_ERROR_PATTERNS):
            cause = "SYNTAX_ERROR"
            confidence = 0.95
            explanation = self._build_explanation(task_id, exit_code, stderr, "SYNTAX_ERROR")
            suggested_action = "human"
            repair = None

        # Missing input
        elif self._matches_any(stderr, MISSING_INPUT_PATTERNS):
            cause = "MISSING_INPUT"
            confidence = 0.9
            explanation = self._build_explanation(task_id, exit_code, stderr, "MISSING_INPUT")
            suggested_action = "retry"
            repair = None

        # Node / network failure
        elif self._matches_any(stderr, NODE_FAIL_PATTERNS):
            cause = "NODE_FAIL"
            confidence = 0.8
            explanation = self._build_explanation(task_id, exit_code, stderr, "NODE_FAIL")
            suggested_action = "retry"
            repair = None

        # Generic failure
        elif exit_code is not None and exit_code != 0:
            cause = "UNKNOWN"
            confidence = 0.5
            explanation = self._build_explanation(task_id, exit_code, stderr, "UNKNOWN")
            suggested_action = "human"
            repair = None

        else:
            cause = "UNKNOWN"
            confidence = 0.3
            explanation = self._build_explanation(task_id, exit_code, stderr, "UNKNOWN")
            suggested_action = "human"
            repair = None

        return Diagnosis(
            task_id=task_id,
            cause=cause,
            confidence=confidence,
            explanation=explanation,
            suggested_action=suggested_action,
            repair=repair,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
        return any(p.search(text) for p in patterns)

    @staticmethod
    def _build_explanation(task_id: str, exit_code: int | None, stderr: str, cause: str) -> str:
        code = str(exit_code) if exit_code is not None else "N/A"
        trunc = stderr[:200].replace("\n", " | ") if stderr else "(no stderr)"
        return f"Task {task_id} failed with exit_code={code}, cause={cause}. stderr: {trunc}"
