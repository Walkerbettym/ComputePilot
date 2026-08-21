"""GROMACS molecular dynamics skill — biomolecular simulation domain knowledge.

Encodes force-field/ensemble vocabulary and parameter constraints for
translating natural-language MD queries into GROMACS workflows.
"""

from __future__ import annotations

from computepilot.models.workflow import Resources
from computepilot.skills.base import ErrorAction, Skill

gromacs_skill = Skill(
    name="gromacs",
    version="1.0.0",
    description=(
        "GROMACS molecular dynamics: protein/lipid/system preparation, "
        "energy minimisation, NVT/NPT equilibration, production MD, "
        "and trajectory analysis (RMSD/RMSF/radius of gyration)."
    ),
    capabilities=[
        "system_preparation",
        "energy_minimisation",
        "nvt_equilibration",
        "npt_equilibration",
        "production_md",
        "rmsd_analysis",
        "free_energy_estimate",
    ],
    constraints={
        "required_commands": ["gmx", "gmx_mpi"],
        "supported_versions": ["2024", "2023", "2022"],
        "max_atoms_single_node": 5000000,
    },
    resources_defaults=Resources(cpu=16, memory="32GB", gpu=1),
    error_handling={
        "OOM": ErrorAction(action="increase_memory", params={"factor": 2.0, "max_memory": "256GB"}),
        "TIMEOUT": ErrorAction(
            action="extend_production", params={"factor": 1.5, "checkpoint_restart": True}
        ),
        "BOND_ERROR": ErrorAction(action="regenerate_topology", params={"use_pdb2gmx": True}),
        "SETTLE_ERROR": ErrorAction(
            action="reduce_timestep", params={"factor": 0.5, "min_dt_fs": 0.5}
        ),
        "MISSING_INPUT": ErrorAction(
            action="fetch_structure", params={"source": "rcsb", "auto_download": True}
        ),
    },
    vocabulary_mappings={
        "force_field": {
            "amber": "amber14",
            "charmm": "charmm36",
            "opls": "oplsaa",
            "gromos": "gromos54a7",
            "martini": "martini3",
        },
        "ensemble": {
            "nvt": "NVT",
            "canonical": "NVT",
            "npt": "NPT",
            "isothermal isobaric": "NPT",
            "nve": "NVE",
            "microcanonical": "NVE",
        },
        "solvent": {
            "tip3p": "TIP3P",
            "spc": "SPC",
            "spce": "SPC/E",
            "water": "TIP3P",
        },
        "analysis_type": {
            "rmsd": "rmsd",
            "root mean square deviation": "rmsd",
            "rmsf": "rmsf",
            "flexibility": "rmsf",
            "radius of gyration": "gyrate",
            "compaction": "gyrate",
            "hydrogen bonds": "hbond",
            "distance matrix": "mdmat",
        },
        "structure_source": {
            "pdb": "rcsb_pdb",
            "protein data bank": "rcsb_pdb",
            "alphafold": "alphafold_db",
        },
    },
    parameter_constraints={
        "temperature_k": {
            "required": True,
            "min_value": 1,
            "max_value": 1000,
            "default": 300,
            "description": "Simulation temperature in Kelvin",
        },
        "timestep_fs": {
            "allowed": [0.5, 1.0, 2.0, 4.0],
            "default": 2.0,
            "description": "Integration timestep (4 fs requires hydrogen mass repartitioning)",
        },
        "duration_ns": {
            "min_value": 0.001,
            "max_value": 10000,
            "default": 100,
            "description": "Production run length in nanoseconds",
        },
        "force_field": {
            "required": True,
            "allowed": ["amber14", "charmm36", "oplsaa", "gromos54a7", "martini3"],
            "description": "Force field for topology generation",
        },
        "gpu": {
            "allowed": [0, 1, 2, 4],
            "default": 1,
            "description": "GPU count for nonbonded acceleration",
        },
    },
    optimization_strategies=[
        "domain_decomposition_autotune",
        "gpu_offload_nonbonded",
        "update_groups_on_gpu",
        "checkpoint_every_15min",
        "skip_energy_minimisation_on_continuation",
    ],
)
