"""Tests for Conductor — multi-turn dialog and clarification loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from computepilot.agent.conductor import Conductor
from computepilot.agent.provider import LLMResponse
from computepilot.models.workflow import Resources
from computepilot.skills.base import Skill, SkillRegistry

# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


@dataclass
class MockProvider:
    """Fake LLM provider that returns canned responses."""

    canned: dict[str, Any] = field(default_factory=dict)

    def generate(self, system_prompt="", user_prompt="", **kwargs):
        return LLMResponse(content="mock response")

    def structured_output(self, output_model, system_prompt="", user_prompt="", **kwargs):
        parsed = output_model(
            verb="run",
            target="genomics",
            parameters={"populations": ["EUR", "AFR"]},
            resources={"cpu": 4, "memory": "8GB", "gpu": 0},
        )
        return LLMResponse(content="", parsed=parsed)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _genomics_registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(
        Skill(
            name="genomics",
            description="Population genetics analysis",
            vocabulary_mappings={
                "population": {
                    "european": "EUR",
                    "african": "AFR",
                    "east asian": "EAS",
                },
                "analysis_type": {
                    "comparison": "population_comparison",
                    "single population": "single_population",
                },
            },
            parameter_constraints={
                "population": {"allowed": ["EUR", "AFR", "EAS"], "required": True},
                "analysis_type": {
                    "allowed": ["population_comparison", "single_population"],
                    "required": True,
                },
            },
            resources_defaults=Resources(cpu=4, memory="8GB", gpu=0),
        )
    )
    return reg


def _conductor() -> Conductor:
    return Conductor(
        provider=MockProvider(),
        registry=_genomics_registry(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConductorSession:
    def test_new_session(self) -> None:
        """Creating a new session returns a valid ID."""
        cond = _conductor()
        sid = cond.new_session()
        assert len(sid) == 12
        assert cond.get_session(sid) is not None

    def test_session_not_found(self) -> None:
        """Unknown session returns clarification response."""
        cond = _conductor()
        resp = cond.turn_sync("nonexistent", "hello")
        assert resp.requires_clarification
        assert "not found" in resp.message.lower()


class TestConductorRouting:
    def test_routing_resolves_vocabulary(self) -> None:
        """First turn resolves vocabulary and routes to a skill."""
        cond = _conductor()
        sid = cond.new_session()
        resp = cond.turn_sync(sid, "European comparison")
        assert resp.phase in ("clarifying", "approval")
        session = cond.get_session(sid)
        assert session is not None
        assert session.selected_skill is not None
        assert session.selected_skill.name == "genomics"

    def test_routing_missing_fields_triggers_clarification(self) -> None:
        """Missing required fields trigger a clarification response."""
        cond = _conductor()
        sid = cond.new_session()
        resp = cond.turn_sync(sid, "european")
        assert resp.requires_clarification, f"Expected clarification but got: {resp.phase}"
        assert "missing" in resp.message.lower() or "Missing" in resp.message
        assert resp.phase == "clarifying"

    def test_clarification_loop_resolves(self) -> None:
        """After clarification, missing fields are resolved and plan is shown."""
        cond = _conductor()
        sid = cond.new_session()
        resp1 = cond.turn_sync(sid, "european")
        assert resp1.requires_clarification

        resp2 = cond.turn_sync(sid, "comparison")
        assert not resp2.requires_clarification, (
            f"Expected approval but got clarification: {resp2.phase}"
        )
        assert resp2.phase == "approval" or resp2.phase == "done"
        assert resp2.workflow_plan is not None or resp2.workflow is not None


class TestConductorApproval:
    def test_approval_accepts(self) -> None:
        """Approving the plan moves session to done."""
        cond = _conductor()
        sid = cond.new_session()
        # First turn with complete info
        resp1 = cond.turn_sync(sid, "european comparison")
        # Should be in approval phase now, or still clarifying
        if resp1.requires_clarification:
            resp1 = cond.turn_sync(sid, "comparison")

        if resp1.phase == "approval":
            resp2 = cond.turn_sync(sid, "yes")
            assert resp2.phase == "done"
            assert "approved" in resp2.message.lower()

    def test_approval_rejects(self) -> None:
        """Rejecting the plan goes back to clarifying."""
        cond = _conductor()
        sid = cond.new_session()
        resp1 = cond.turn_sync(sid, "european comparison")
        if resp1.requires_clarification:
            resp1 = cond.turn_sync(sid, "comparison")

        if resp1.phase == "approval":
            resp2 = cond.turn_sync(sid, "no")
            assert resp2.requires_clarification
            assert resp2.phase == "clarifying"


class TestConductorDoneSubsequentTurn:
    def test_done_session_returns_info_message(self) -> None:
        """After completion, another turn tells user to start new session."""
        cond = _conductor()
        sid = cond.new_session()
        resp1 = cond.turn_sync(sid, "european comparison")
        if resp1.requires_clarification:
            resp1 = cond.turn_sync(sid, "comparison")

        if resp1.phase == "approval":
            _ = cond.turn_sync(sid, "yes")

        resp_last = cond.turn_sync(sid, "what now?")
        assert "new session" in resp_last.message.lower()
