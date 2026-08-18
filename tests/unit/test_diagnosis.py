"""Tests for Diagnoser — failure classification and repair suggestions."""

from __future__ import annotations

from sciflow.agent.diagnosis import Diagnoser, RepairSpec


class TestDiagnoser:
    """Unit tests for Diagnoser."""

    def setup_method(self) -> None:
        self.diagnoser = Diagnoser()

    # --- OOM ---

    def test_oom_exit_137(self) -> None:
        d = self.diagnoser.diagnose("task-1", exit_code=137)
        assert d.cause == "OOM"
        assert d.confidence >= 0.9
        assert d.suggested_action == "repair"
        assert d.repair is not None
        assert d.repair.action == "increase_memory"
        assert d.repair.params["factor"] == 2.0

    def test_oom_stderr_killed(self) -> None:
        d = self.diagnoser.diagnose("task-2", exit_code=1, stderr="Killed")
        assert d.cause == "OOM"
        assert d.repair is not None
        assert d.repair.action == "increase_memory"

    def test_oom_stderr_out_of_memory(self) -> None:
        d = self.diagnoser.diagnose("task-3", exit_code=1, stderr="out of memory")
        assert d.cause == "OOM"
        assert d.confidence >= 0.8

    def test_oom_stderr_oom(self) -> None:
        d = self.diagnoser.diagnose("task-4", exit_code=1, stderr="OOM killed")
        assert d.cause == "OOM"

    def test_oom_stderr_cannot_allocate(self) -> None:
        d = self.diagnoser.diagnose("task-5", exit_code=1, stderr="cannot allocate memory")
        assert d.cause == "OOM"

    # --- TIMEOUT ---

    def test_timeout_stderr(self) -> None:
        d = self.diagnoser.diagnose("task-6", exit_code=1, stderr="DUE TO TIME")
        assert d.cause == "TIMEOUT"
        assert d.confidence >= 0.85
        assert d.suggested_action == "repair"
        assert d.repair is not None
        assert d.repair.action == "increase_walltime"
        assert d.repair.params["factor"] == 1.5

    def test_timeout_stderr_timed_out(self) -> None:
        d = self.diagnoser.diagnose("task-7", exit_code=1, stderr="timed out")
        assert d.cause == "TIMEOUT"

    def test_timeout_stderr_exceeded_time(self) -> None:
        d = self.diagnoser.diagnose("task-8", exit_code=1, stderr="exceeded max time")
        assert d.cause == "TIMEOUT"

    # --- MISSING_INPUT ---

    def test_missing_input_no_such_file(self) -> None:
        d = self.diagnoser.diagnose("task-9", exit_code=1, stderr="No such file or directory")
        assert d.cause == "MISSING_INPUT"
        assert d.suggested_action == "retry"
        assert d.repair is None

    def test_missing_input_file_not_found(self) -> None:
        d = self.diagnoser.diagnose("task-10", exit_code=1, stderr="file not found")
        assert d.cause == "MISSING_INPUT"

    # --- SYNTAX_ERROR ---

    def test_syntax_error(self) -> None:
        d = self.diagnoser.diagnose("task-11", exit_code=1, stderr="SyntaxError: invalid syntax")
        assert d.cause == "SYNTAX_ERROR"
        assert d.confidence >= 0.95
        assert d.suggested_action == "human"
        assert d.repair is None

    def test_name_error(self) -> None:
        d = self.diagnoser.diagnose("task-12", exit_code=1, stderr="NameError: x not defined")
        assert d.cause == "SYNTAX_ERROR"

    def test_command_not_found(self) -> None:
        d = self.diagnoser.diagnose("task-13", exit_code=127, stderr="command not found")
        assert d.cause == "SYNTAX_ERROR"

    # --- NODE_FAIL ---

    def test_node_fail(self) -> None:
        d = self.diagnoser.diagnose("task-14", exit_code=1, stderr="node fail")
        assert d.cause == "NODE_FAIL"
        assert d.suggested_action == "retry"
        assert d.repair is None

    def test_connection_refused(self) -> None:
        d = self.diagnoser.diagnose("task-15", exit_code=1, stderr="connection refused")
        assert d.cause == "NODE_FAIL"

    # --- UNKNOWN ---

    def test_unknown_exit_code(self) -> None:
        d = self.diagnoser.diagnose("task-16", exit_code=1, stderr="something went wrong")
        assert d.cause == "UNKNOWN"
        assert d.confidence == 0.5
        assert d.suggested_action == "human"
        assert d.repair is None

    def test_no_exit_code_no_stderr(self) -> None:
        d = self.diagnoser.diagnose("task-17", exit_code=None, stderr="")
        assert d.cause == "UNKNOWN"
        assert d.confidence == 0.3
        assert d.suggested_action == "human"

    # --- RepairSpec ---

    def test_repair_spec_defaults(self) -> None:
        spec = RepairSpec(action="increase_memory")
        assert spec.params == {}


class TestDiagnosis:
    """Unit tests for the Diagnosis dataclass."""

    def test_diagnosis_fields(self) -> None:
        from sciflow.agent.diagnosis import Diagnosis

        diag = Diagnosis(
            task_id="t1",
            cause="OOM",
            confidence=0.95,
            explanation="OOM detected",
            suggested_action="repair",
            repair=RepairSpec(action="increase_memory", params={"factor": 2.0}),
        )
        assert diag.task_id == "t1"
        assert diag.cause == "OOM"
        assert diag.confidence == 0.95
        assert diag.repair is not None
        assert diag.repair.action == "increase_memory"

    def test_diagnosis_no_repair(self) -> None:
        from sciflow.agent.diagnosis import Diagnosis

        diag = Diagnosis(
            task_id="t2",
            cause="UNKNOWN",
            confidence=0.3,
            explanation="no clue",
            suggested_action="human",
        )
        assert diag.repair is None
