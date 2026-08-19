"""Conductor — multi-turn dialog orchestrator for workflow planning.

Implements the paper's Conductor agent: the user-facing entry point
that routes queries, manages clarification loops, and enforces
human-in-the-loop validation gates.

Typical session::

    cond = Conductor(provider, planner, registry)
    session_id = cond.new_session()

    # Turn 1: initial query
    resp = await cond.turn(session_id, "Run population comparison")

    if resp.requires_clarification:
        # "Which populations to compare? (european, african, ...)"
        resp = await cond.turn(
            session_id,
            "European and African on chromosome 22"
        )

    # Now session has a complete Intent + WorkflowPlan
    print(resp.workflow_plan)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from computepilot.agent.cost import CostEstimator
from computepilot.agent.intent import Intent
from computepilot.agent.planner import Planner
from computepilot.agent.provider import LLMProvider
from computepilot.agent.vocabulary import VocabularyResolver
from computepilot.models.workflow import Workflow
from computepilot.policy.engine import PolicyEngine
from computepilot.runtime.sentinel import ExecutionSentinel
from computepilot.skills.base import Skill, SkillRegistry


@dataclass
class TurnResponse:
    """Response from a single conversation turn."""

    message: str
    session_id: str
    requires_clarification: bool = False
    missing_fields: list[str] = field(default_factory=list)
    suggested_values: dict[str, list[str]] = field(default_factory=dict)
    workflow_plan: str | None = None
    workflow: Workflow | None = None
    cost_estimate: str | None = None
    phase: str = "routing"


@dataclass
class ConductorSession:
    """A multi-turn conversation session."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    history: list[dict[str, str]] = field(default_factory=list)
    current_intent: Intent | None = None
    selected_skill: Skill | None = None
    phase: str = "routing"  # routing → clarifying → planning → approval → done
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class Conductor:
    """Multi-turn conversation orchestrator for workflow planning.

    Usage::

        conductor = Conductor(llm_provider, planner, skill_registry)
        session_id = conductor.new_session()
        resp = conductor.turn_sync(
            session_id,
            "Run population comparison between European and African"
        )
        if resp.requires_clarification:
            # Ask user for missing fields, then continue...
            resp = conductor.turn_sync(session_id, "comparison of all variants")
    """

    def __init__(
        self,
        provider: LLMProvider,
        planner: Planner | None = None,
        registry: SkillRegistry | None = None,
        vocab_resolver: VocabularyResolver | None = None,
        cost_estimator: CostEstimator | None = None,
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self._provider = provider
        self._planner = planner or Planner()
        self._registry = registry or SkillRegistry()
        self._vocab = vocab_resolver or VocabularyResolver(registry)
        self._cost = cost_estimator or CostEstimator()
        self._policy = policy_engine or PolicyEngine()
        self._sessions: dict[str, ConductorSession] = {}
        self._sentinel: ExecutionSentinel | None = None

    @property
    def sentinel(self) -> ExecutionSentinel | None:
        """The attached Executionsentinel, or None."""
        return self._sentinel

    def attach_sentinel(self, sentinel: ExecutionSentinel) -> None:
        """Attach an ExecutionSentinel for progress monitoring."""
        self._sentinel = sentinel

    # -- Session management ---------------------------------------------------

    def new_session(self) -> str:
        """Create a new conversation session and return its ID."""
        session = ConductorSession()
        self._sessions[session.id] = session
        return session.id

    def get_session(self, session_id: str) -> ConductorSession | None:
        """Return a session by ID, or None."""
        return self._sessions.get(session_id)

    # -- Single turn (synchronous, for testing / simple use) ------------------

    def turn_sync(
        self,
        session_id: str,
        user_input: str,
    ) -> TurnResponse:
        """Process a single user turn synchronously.

        Uses the LLM provider for intent extraction when available;
        falls back to rule-based vocabulary resolution otherwise.
        """
        return self._process_turn(session_id, user_input)

    async def turn(
        self,
        session_id: str,
        user_input: str,
    ) -> TurnResponse:
        """Process a single user turn."""
        return self._process_turn(session_id, user_input)

    # -- Internal processing --------------------------------------------------

    def _process_turn(
        self,
        session_id: str,
        user_input: str,
    ) -> TurnResponse:
        """Core turn processing (shared by sync and async)."""
        session = self._sessions.get(session_id)
        if session is None:
            return TurnResponse(
                message=f"Session {session_id} not found.",
                session_id=session_id,
                requires_clarification=True,
            )

        session.history.append({"role": "user", "content": user_input})

        # --- Phase: routing (first turn) ---
        if session.phase == "routing" or session.current_intent is None:
            return self._handle_routing(session, user_input)

        # --- Phase: clarifying ---
        if session.phase == "clarifying":
            return self._handle_clarifying(session, user_input)

        # --- Phase: approval ---
        if session.phase == "approval":
            return self._handle_approval(session, user_input)

        # --- Phase: done ---
        return TurnResponse(
            message="Session is complete. Start a new session with new_session().",
            session_id=session_id,
        )

    def _handle_routing(
        self,
        session: ConductorSession,
        user_input: str,
    ) -> TurnResponse:
        """Route the initial query: detect domain, resolve vocabulary."""
        # 1. Resolve vocabulary via Skills
        vocab_result = self._vocab.resolve(user_input)

        # 2. Select a skill based on resolved vocabulary
        # Pick the skill with the most matches
        skill_scores: dict[str, dict[str, Any]] = {}
        for rt in vocab_result.resolved:
            if rt.skill_name not in skill_scores:
                skill_scores[rt.skill_name] = {"skill": None, "score": 0}
            skill_scores[rt.skill_name]["score"] += 1

        best_skill_name = (
            max(skill_scores, key=lambda k: skill_scores[k]["score"]) if skill_scores else None
        )
        selected_skill: Skill | None = None
        if best_skill_name:
            selected_skill = self._registry.get(best_skill_name)

        session.selected_skill = selected_skill

        # 3. Build a partial intent from resolved vocabulary
        field_mapping = {
            "population": "populations",
            "analysis_type": "analysis_type",
            "region": "chromosomes",
        }
        params: dict[str, Any] = {}
        for rt in vocab_result.resolved:
            target_key = field_mapping.get(rt.domain_field, rt.domain_field)
            # Collect values, allow list
            if target_key in params:
                existing = params[target_key]
                if isinstance(existing, list):
                    existing.append(rt.code)
                else:
                    params[target_key] = [existing, rt.code]
            else:
                params[target_key] = [rt.code] if rt.domain_field == "population" else rt.code

        resources = {"cpu": 1, "memory": "2GB", "gpu": 0}
        if selected_skill:
            resources = {
                "cpu": selected_skill.resources_defaults.cpu,
                "memory": selected_skill.resources_defaults.memory,
                "gpu": selected_skill.resources_defaults.gpu,
            }

        intent = Intent(
            verb="run",
            target=selected_skill.name if selected_skill else "workflow",
            parameters=params,
            resources=resources,
        )
        session.current_intent = intent

        # 4. Detect missing required fields from skill constraints
        missing: list[str] = []
        if selected_skill and selected_skill.parameter_constraints:
            for field_name, constraint in selected_skill.parameter_constraints.items():
                if constraint.get("required", False) and field_name not in params:
                    missing.append(field_name)

        # 5. Build skill description message
        skill_desc = f"Route to skill: **{selected_skill.name}**" if selected_skill else ""
        if vocab_result.unresolved:
            skill_desc += f"\nUnrecognized terms: {', '.join(vocab_result.unresolved)}"

        if missing:
            session.phase = "clarifying"
            # Suggest possible values from skill constraints
            suggestions: dict[str, list[str]] = {}
            assert selected_skill is not None  # checked above
            for f in missing:
                constraint = selected_skill.parameter_constraints.get(f, {})
                allowed = constraint.get("allowed", [])
                if allowed:
                    suggestions[f] = allowed

                # Also include vocabulary mappings
                if selected_skill and f in selected_skill.vocabulary_mappings:
                    mapping_vals = list(selected_skill.vocabulary_mappings[f].values())
                    if mapping_vals:
                        if f in suggestions:
                            suggestions[f].extend(mapping_vals)
                        else:
                            suggestions[f] = mapping_vals

            msg_parts = [skill_desc, f"\nMissing required field(s): {', '.join(missing)}"]
            for f, vals in suggestions.items():
                msg_parts.append(f"  - {f}: {', '.join(vals)}")
            msg_parts.append("\nPlease provide the missing information.")

            return TurnResponse(
                message="\n".join(msg_parts),
                session_id=session.id,
                requires_clarification=True,
                missing_fields=missing,
                suggested_values=suggestions,
                phase="clarifying",
            )

        # 6. No missing fields → go to approval
        return self._to_approval(session)

    def _handle_clarifying(
        self,
        session: ConductorSession,
        user_input: str,
    ) -> TurnResponse:
        """Handle a clarifying turn: update intent with user's input."""
        # Try to resolve new vocabulary from the clarification response
        if session.selected_skill:
            vocab_result = self._vocab.resolve(user_input)

            if session.current_intent:
                # Merge resolved values into parameters
                for rt in vocab_result.resolved:
                    target_key = rt.domain_field
                    if target_key in ("population",):
                        if "populations" not in session.current_intent.parameters:
                            session.current_intent.parameters["populations"] = []
                        if isinstance(session.current_intent.parameters["populations"], list):
                            session.current_intent.parameters["populations"].append(rt.code)
                        elif rt.code not in str(session.current_intent.parameters["populations"]):
                            session.current_intent.parameters["populations"] = [
                                session.current_intent.parameters["populations"],
                                rt.code,
                            ]
                    else:
                        # For other fields like analysis_type
                        existing = session.current_intent.parameters.get(target_key)
                        if not existing:
                            session.current_intent.parameters[target_key] = rt.code

        # Re-check missing fields
        missing = self._check_missing_fields(session)
        if missing:
            return TurnResponse(
                message=f"Still missing: {', '.join(missing)}. Please provide them.",
                session_id=session.id,
                requires_clarification=True,
                missing_fields=missing,
                phase="clarifying",
            )

        return self._to_approval(session)

    def _check_missing_fields(self, session: ConductorSession) -> list[str]:
        """Re-check which required fields are still missing."""
        missing: list[str] = []
        skill = session.selected_skill
        if not skill or not skill.parameter_constraints:
            return missing

        params = session.current_intent.parameters if session.current_intent else {}

        # Same field_mapping as _handle_routing — keeps param keys consistent
        field_mapping = {
            "population": "populations",
            "analysis_type": "analysis_type",
            "region": "chromosomes",
        }
        for field_name, constraint in skill.parameter_constraints.items():
            if not constraint.get("required", False):
                continue
            param_key = field_mapping.get(field_name, field_name)
            if param_key not in params or not params.get(param_key):
                missing.append(field_name)

        return missing

    def _to_approval(self, session: ConductorSession) -> TurnResponse:
        """Generate workflow plan and move to approval phase."""
        if session.current_intent is None:
            return TurnResponse(
                message="Cannot generate plan: no intent available.",
                session_id=session.id,
                requires_clarification=True,
                phase="clarifying",
            )

        # Generate workflow
        workflow = self._planner.plan(session.current_intent)
        cost = self._cost.estimate(workflow)

        cost_str = f"Estimated cost: ${cost.total_cost:.2f} {cost.currency}"

        plan_lines = [f"**Workflow plan** ({workflow.name}):"]
        for i, task in enumerate(workflow.tasks, 1):
            deps = f" [after: {', '.join(task.depends_on)}]" if task.depends_on else ""
            plan_lines.append(f"  {i}. **{task.id}** — {task.command}{deps}")
        plan_lines.append("")
        plan_lines.append(cost_str)

        session.phase = "approval"

        return TurnResponse(
            message="\n".join(plan_lines),
            session_id=session.id,
            workflow_plan="\n".join(plan_lines),
            workflow=workflow,
            cost_estimate=cost_str,
            phase="approval",
        )

    def _handle_approval(
        self,
        session: ConductorSession,
        user_input: str,
    ) -> TurnResponse:
        """Handle approval: accept or reject the plan."""
        affirmation = user_input.strip().lower() in ("yes", "y", "approve", "go", "ok")
        if affirmation:
            session.phase = "done"
            return TurnResponse(
                message="✅ Workflow approved. You can now run it with `cpilot run`.",
                session_id=session.id,
                workflow=session.current_intent
                and self._planner.plan(session.current_intent)
                or None,
                phase="done",
            )

        session.phase = "clarifying"
        return TurnResponse(
            message="Plan rejected. Please describe what you'd like to change.",
            session_id=session.id,
            requires_clarification=True,
            phase="clarifying",
        )
