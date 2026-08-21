"""OpenFOAM CFD skill — incompressible/compressible flow simulation domain knowledge.

Encodes solver vocabulary, turbulence-model mappings, and parameter
constraints so natural-language CFD queries route to executable workflows.
"""

from __future__ import annotations

from computepilot.models.workflow import Resources
from computepilot.skills.base import ErrorAction, Skill

openfoam_skill = Skill(
    name="openfoam",
    version="1.0.0",
    description=(
        "OpenFOAM computational fluid dynamics: steady/transient incompressible "
        "and compressible flow, meshing with blockMesh/snappyHexMesh, "
        "and post-processing with Paraview/function objects."
    ),
    capabilities=[
        "steady_incompressible",
        "transient_incompressible",
        "compressible_flow",
        "multiphase_flow",
        "mesh_generation",
        "residual_monitoring",
        "force_coefficients",
    ],
    constraints={
        "required_commands": ["blockMesh", "simpleFoam", "pimpleFoam", "foamPostProcess"],
        "supported_versions": ["v2312", "11", "10"],
        "max_parallel_cores": 512,
    },
    resources_defaults=Resources(cpu=8, memory="16GB", gpu=0),
    error_handling={
        "OOM": ErrorAction(action="increase_memory", params={"factor": 2.0, "max_memory": "128GB"}),
        "TIMEOUT": ErrorAction(
            action="increase_walltime", params={"factor": 1.5, "max_walltime_hours": 48}
        ),
        "DIVERGENCE": ErrorAction(
            action="reduce_timestep",
            params={"factor": 0.5, "min_delta_t": 1e-6, "relax_last": 0.7},
        ),
        "MESH_ERROR": ErrorAction(action="regenerate_mesh", params={"check_mesh": True}),
        "MISSING_INPUT": ErrorAction(action="stage_data", params={"auto_download": True}),
    },
    vocabulary_mappings={
        "solver": {
            "simple": "simpleFoam",
            "steady": "simpleFoam",
            "pimple": "pimpleFoam",
            "transient": "pimpleFoam",
            "unsteady": "pimpleFoam",
            "ico": "icoFoam",
            "laminar pipe": "icoFoam",
            "rho central": "rhoCentralFoam",
            "compressible": "rhoCentralFoam",
            "supersonic": "rhoCentralFoam",
            "inter": "interFoam",
            "multiphase": "interFoam",
            "free surface": "interFoam",
            "buoyant": "buoyantPimpleFoam",
            "natural convection": "buoyantBoussinesqPimpleFoam",
        },
        "turbulence_model": {
            "kepsilon": "kEpsilon",
            "k epsilon": "kEpsilon",
            "komega": "kOmegaSST",
            "sst": "kOmegaSST",
            "k omega sst": "kOmegaSST",
            "les": "LES",
            "smagorinsky": "Smagorinsky",
            "wale": "WALE",
            "laminar": "laminar",
            "spalart allmaras": "SpalartAllmaras",
        },
        "boundary_type": {
            "no slip wall": "noSlip",
            "wall": "noSlip",
            "inlet velocity": "fixedValue",
            "outlet pressure": "zeroGradient",
            "symmetry": "symmetryPlane",
            "far field": "freestream",
            "periodic": "cyclic",
        },
        "mesh_tool": {
            "block mesh": "blockMesh",
            "structured hex": "blockMesh",
            "snappy": "snappyHexMesh",
            "complex geometry": "snappyHexMesh",
            "cfmesh": "cfMesh",
        },
    },
    parameter_constraints={
        "reynolds": {
            "required": False,
            "min_value": 1,
            "max_value": 100000000,
            "description": "Target Reynolds number; sets inlet velocity or viscosity",
        },
        "turbulence_model": {
            "allowed": [
                "kEpsilon",
                "kOmegaSST",
                "LES",
                "Smagorinsky",
                "WALE",
                "SpalartAllmaras",
                "laminar",
            ],
            "default": "kOmegaSST",
            "description": "RANS/LES closure model",
        },
        "solver": {
            "required": True,
            "allowed": [
                "simpleFoam",
                "pimpleFoam",
                "icoFoam",
                "rhoCentralFoam",
                "interFoam",
                "buoyantPimpleFoam",
                "buoyantBoussinesqPimpleFoam",
            ],
            "description": "OpenFOAM solver application",
        },
        "parallel_cores": {
            "allowed": [1, 2, 4, 8, 16, 32, 64, 128],
            "default": 4,
            "description": "MPI ranks via decomposePar",
        },
    },
    optimization_strategies=[
        "decomposepar_autotune",
        "writeinterval_reduce_io",
        "adjust_time_step_by_courant",
        "function_objects_over_postmortem",
        "residual_early_exit",
    ],
)
