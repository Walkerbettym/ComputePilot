"""LAMMPS materials skill — atomistic/condensed-matter simulation domain knowledge.

Encodes potential/ensemble vocabulary and parameter constraints for
translating natural-language materials queries into LAMMPS workflows.
"""

from __future__ import annotations

from computepilot.models.workflow import Resources
from computepilot.skills.base import ErrorAction, Skill

lammps_skill = Skill(
    name="lammps",
    version="1.0.0",
    description=(
        "LAMMPS molecular dynamics for materials: EAM/Tersoff/REAXFF potentials, "
        "NVE/NVT/NPT ensembles, tensile/shear loading, thermal conductivity, "
        "and defect analysis."
    ),
    capabilities=[
        "bulk_crystal_equilibration",
        "tensile_loading",
        "shear_deformation",
        "thermal_conductivity",
        "point_defect_analysis",
        "dislocation_dynamics",
        "amorphous_quench",
    ],
    constraints={
        "required_commands": ["lmp", "lmp_mpi"],
        "supported_versions": ["2024", "2023", "2Aug2023"],
        "max_atoms_gpu": 10000000,
    },
    resources_defaults=Resources(cpu=32, memory="64GB", gpu=1),
    error_handling={
        "OOM": ErrorAction(action="increase_memory", params={"factor": 2.0, "max_memory": "256GB"}),
        "TIMEOUT": ErrorAction(
            action="extend_run", params={"factor": 1.5, "restart_every_n_steps": 100000}
        ),
        "LOST_ATOMS": ErrorAction(
            action="enlarge_boundary", params={"ghost_factor": 1.2, "reneighbor_check": True}
        ),
        "ENERGY_BLOWUP": ErrorAction(
            action="reduce_timestep", params={"factor": 0.5, "min_dt_fs": 0.1}
        ),
        "MISSING_POTENTIAL": ErrorAction(
            action="fetch_potential", params={"source": "nist_interatomic", "auto_download": True}
        ),
    },
    vocabulary_mappings={
        "potential": {
            "eam": "EAM",
            "embedded atom": "EAM",
            "tersoff": "Tersoff",
            "stillinger weber": "SW",
            "sw": "SW",
            "lennard jones": "lj/cut",
            "lj": "lj/cut",
            "reaxff": "REAXFF",
            "reactive force field": "REAXFF",
            "meam": "MEAM",
            "morse": "morse",
            "airebo": "AIREBO",
            "graphite potential": "AIREBO",
        },
        "ensemble": {
            "nve": "nve",
            "microcanonical": "nve",
            "nvt": "nvt",
            "nose hoover": "nvt",
            "npt": "npt",
            "isobaric": "npt",
            "langevin": "nve+langavin",
        },
        "material": {
            "copper": "Cu",
            "cu": "Cu",
            "iron": "Fe",
            "fe": "Fe",
            "silicon": "Si",
            "si": "Si",
            "nickel": "Ni",
            "graphene": "graphene",
            "tungsten": "W",
            "aluminium": "Al",
            "aluminum": "Al",
        },
        "loading_mode": {
            "tension": "tensile",
            "uniaxial tension": "tensile",
            "compression": "compressive",
            "shear": "shear",
            "nanoindentation": "indentation",
        },
        "analysis_type": {
            "thermal conductivity": "green_kubo",
            "green kubo": "green_kubo",
            "nemd": "nemd",
            "stress strain curve": "stress_strain",
            "radial distribution": "rdf",
            "pair correlation": "rdf",
            "mean square displacement": "msd",
            "diffusion": "msd",
        },
    },
    parameter_constraints={
        "temperature_k": {
            "required": True,
            "min_value": 0.1,
            "max_value": 6000,
            "default": 300,
            "description": "Target temperature in Kelvin",
        },
        "potential": {
            "required": True,
            "allowed": ["EAM", "Tersoff", "SW", "lj/cut", "REAXFF", "MEAM", "morse", "AIREBO"],
            "description": "Interatomic potential style",
        },
        "atom_count": {
            "min_value": 100,
            "max_value": 1000000000,
            "default": 100000,
            "description": "Number of atoms in the simulation box",
        },
        "strain_rate": {
            "min_value": 1000000,
            "max_value": 10000000000,
            "default": 1000000000,
            "description": "Deformation rate in 1/s (MD requires high rates)",
        },
    },
    optimization_strategies=[
        "neighbor_bin_rebuild_autotune",
        "pppm_longrange_when_charged",
        "gpu_package_for_pair_styles",
        "balance_load_after_defect_insertion",
        "restart_files_for_recovery",
    ],
)
