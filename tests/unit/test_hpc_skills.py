"""Tests for v0.5 HPC domain skills (openfoam / gromacs / lammps) + Conductor routing."""

from __future__ import annotations

import pytest

from computepilot.agent.conductor import Conductor
from computepilot.skills.base import SkillRegistry


@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register_builtins()
    return reg


class TestOpenFoamSkill:
    def test_registered(self, registry: SkillRegistry) -> None:
        skill = registry.get("openfoam")
        assert skill is not None
        assert "steady_incompressible" in skill.capabilities

    @pytest.mark.parametrize(
        ("token", "expected"),
        [("steady", "simpleFoam"), ("transient", "pimpleFoam"), ("sst", "kOmegaSST")],
    )
    def test_vocabulary(self, registry: SkillRegistry, token: str, expected: str) -> None:
        assert registry.get("openfoam") is not None
        resolved = registry.get("openfoam")
        assert resolved is not None
        assert resolved.resolve_vocabulary(token) == expected

    def test_required_solver_constraint(self, registry: SkillRegistry) -> None:
        skill = registry.get("openfoam")
        assert skill is not None
        constraints = skill.parameter_constraints["solver"]
        assert constraints["required"] is True
        assert "simpleFoam" in constraints["allowed"]

    def test_divergence_error_action(self, registry: SkillRegistry) -> None:
        skill = registry.get("openfoam")
        assert skill is not None
        action = skill.error_handling["DIVERGENCE"]
        assert action.action == "reduce_timestep"


class TestGromacsSkill:
    def test_registered(self, registry: SkillRegistry) -> None:
        skill = registry.get("gromacs")
        assert skill is not None
        assert "production_md" in skill.capabilities

    @pytest.mark.parametrize(
        ("token", "expected"),
        [("amber", "amber14"), ("charmm", "charmm36"), ("npt", "NPT"), ("tip3p", "TIP3P")],
    )
    def test_vocabulary(self, registry: SkillRegistry, token: str, expected: str) -> None:
        skill = registry.get("gromacs")
        assert skill is not None
        assert skill.resolve_vocabulary(token) == expected

    def test_temperature_default(self, registry: SkillRegistry) -> None:
        skill = registry.get("gromacs")
        assert skill is not None
        assert skill.parameter_constraints["temperature_k"]["default"] == 300

    def test_gpu_resources_default(self, registry: SkillRegistry) -> None:
        skill = registry.get("gromacs")
        assert skill is not None
        assert skill.resources_defaults.gpu == 1


class TestLammpsSkill:
    def test_registered(self, registry: SkillRegistry) -> None:
        skill = registry.get("lammps")
        assert skill is not None
        assert "tensile_loading" in skill.capabilities

    @pytest.mark.parametrize(
        ("token", "expected"),
        [("eam", "EAM"), ("reaxff", "REAXFF"), ("tension", "tensile"), ("graphene", "graphene")],
    )
    def test_vocabulary(self, registry: SkillRegistry, token: str, expected: str) -> None:
        skill = registry.get("lammps")
        assert skill is not None
        assert skill.resolve_vocabulary(token) == expected

    def test_potential_required(self, registry: SkillRegistry) -> None:
        skill = registry.get("lammps")
        assert skill is not None
        assert skill.parameter_constraints["potential"]["required"] is True

    def test_lost_atoms_recovery(self, registry: SkillRegistry) -> None:
        skill = registry.get("lammps")
        assert skill is not None
        assert skill.error_handling["LOST_ATOMS"].action == "enlarge_boundary"


class TestConductorRouting:
    def test_routes_openfoam_query(self, registry: SkillRegistry) -> None:
        conductor = Conductor(provider=None, registry=registry)
        sid = conductor.new_session()
        resp = conductor.turn_sync(sid, "cylinder flow simulation with sst turbulence")
        session = conductor.get_session(sid)
        assert session is not None
        assert session.selected_skill is not None
        assert session.selected_skill.name == "openfoam"
        assert resp.missing_fields == ["solver"]
        assert resp.phase == "clarifying"

    def test_routes_lammps_query(self, registry: SkillRegistry) -> None:
        conductor = Conductor(provider=None, registry=registry)
        sid = conductor.new_session()
        conductor.turn_sync(sid, "eam tension simulation of copper at temperature 300")
        session = conductor.get_session(sid)
        assert session is not None
        if session.selected_skill is not None:
            assert session.selected_skill.name == "lammps"

    def test_full_openfoam_flow_to_approval(self, registry: SkillRegistry) -> None:
        conductor = Conductor(provider=None, registry=registry)
        sid = conductor.new_session()
        r1 = conductor.turn_sync(sid, "sst turbulence flow over a step geometry")
        assert r1.requires_clarification
        assert r1.missing_fields == ["solver"]
        r2 = conductor.turn_sync(sid, "use the pimple solver")
        session = conductor.get_session(sid)
        assert session is not None
        assert session.current_intent is not None
        if r2.phase == "approval":
            assert session.current_intent.parameters.get("solver") == "pimpleFoam"
        else:
            assert r2.requires_clarification

    def test_population_genetics_still_routes(self, registry: SkillRegistry) -> None:
        conductor = Conductor(provider=None, registry=registry)
        sid = conductor.new_session()
        conductor.turn_sync(sid, "compare european and african populations on chromosome 22")
        session = conductor.get_session(sid)
        assert session is not None
        assert session.selected_skill is not None
        assert session.selected_skill.name == "population_genetics"
