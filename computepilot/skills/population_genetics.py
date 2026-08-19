"""Population genetics skill — aligned with the paper's 1000 Genomes use case.

This skill encodes the domain knowledge needed to translate natural-language
population genetics queries into executable workflow parameters.
"""

from __future__ import annotations

from computepilot.models.workflow import Resources
from computepilot.skills.base import ErrorAction, Skill

population_genetics_skill = Skill(
    name="population_genetics",
    version="1.0.0",
    description=(
        "Population genetics analysis using 1000 Genomes data. "
        "Supports single-population analysis, population comparison, "
        "and region-specific variant analysis."
    ),
    capabilities=[
        "single_population_analysis",
        "population_comparison",
        "region_analysis",
        "variant_calling",
        "population_statistics",
    ],
    constraints={
        "required_commands": ["python3", "bcftools", "vcftools"],
        "genome_build": "GRCh38",
        "max_populations": 5,
    },
    resources_defaults=Resources(
        cpu=8,
        memory="16GB",
        gpu=0,
    ),
    error_handling={
        "OOM": ErrorAction(action="increase_memory", params={"factor": 2.0, "max_memory": "128GB"}),
        "TIMEOUT": ErrorAction(
            action="increase_walltime",
            params={"factor": 1.5, "max_walltime_hours": 48},
        ),
        "MISSING_INPUT": ErrorAction(action="stage_data", params={"auto_download": True}),
    },
    # -- v0.2 knowledge-layer extensions --
    vocabulary_mappings={
        "population": {
            "european": "EUR",
            "african": "AFR",
            "east asian": "EAS",
            "south asian": "SAS",
            "american": "AMR",
            "admixed american": "AMR",
            "african caribbean": "ACB",
            "african ancestry in southwest us": "ASW",
            "bengali in bangladesh": "BEB",
            "colombian in medellin colombia": "CLM",
            "espanol in puerto rico": "PUR",
            "español en puerto rico": "PUR",
            "chinese dai in xishuangbanna china": "CDX",
            "han chinese in beijing china": "CHB",
            "southern han chinese": "CHS",
            "gujarati indian in houston tx": "GIH",
            "japanese in tokyo japan": "JPT",
            "kipo": "MSL",
            "mende in sierra leone": "MSL",
            "mexican ancestry in los angeles ca": "MXL",
            "peruvian in lima peru": "PEL",
            "punjabi in lahore pakistan": "PJL",
            "sri lankan tamil in uk": "STU",
            "toscani in italia": "TSI",
            "yoruba in ibadan nigeria": "YRI",
            "luhya in webuye kenya": "LWK",
            "gambian in western division gambia": "GWD",
            "iberian populations in spain": "IBS",
            "british in england and scotland": "GBR",
            "finnish in finland": "FIN",
            "utah residents with northern and western european ancestry": "CEU",
        },
        "analysis_type": {
            "comparison": "population_comparison",
            "compare": "population_comparison",
            "single population": "single_population",
            "single": "single_population",
            "region analysis": "region_analysis",
            "region": "region_analysis",
            "variant calling": "variant_calling",
            "call variants": "variant_calling",
            "statistics": "population_statistics",
            "stats": "population_statistics",
        },
        "region": {
            "chromosome 1": "chr1",
            "chromosome 2": "chr2",
            "chromosome 3": "chr3",
            "chromosome 4": "chr4",
            "chromosome 5": "chr5",
            "chromosome 6": "chr6",
            "chromosome 7": "chr7",
            "chromosome 8": "chr8",
            "chromosome 9": "chr9",
            "chromosome 10": "chr10",
            "chromosome 11": "chr11",
            "chromosome 12": "chr12",
            "chromosome 13": "chr13",
            "chromosome 14": "chr14",
            "chromosome 15": "chr15",
            "chromosome 16": "chr16",
            "chromosome 17": "chr17",
            "chromosome 18": "chr18",
            "chromosome 19": "chr19",
            "chromosome 20": "chr20",
            "chromosome 21": "chr21",
            "chromosome 22": "chr22",
            "chromosome x": "chrX",
            "chromosome y": "chrY",
            "chromosome m": "chrM",
        },
        "variant_type": {
            "all variants": "all",
            "all": "all",
            "deleterious": "deleterious",
            "rare": "rare",
            "common": "common",
            "deleterious variants": "deleterious",
            "rare variants": "rare",
            "common variants": "common",
        },
        "data_source": {
            "1000 genomes": "1k_genomes",
            "1kg": "1k_genomes",
            "hail": "hail",
            "gnomad": "gnomad",
        },
    },
    parameter_constraints={
        "population": {
            "required": True,
            "allowed": ["EUR", "AFR", "EAS", "SAS", "AMR"],
            "min_items": 1,
            "max_items": 5,
            "description": "1000 Genomes super-population codes",
        },
        "analysis_type": {
            "required": True,
            "allowed": [
                "single_population",
                "population_comparison",
                "region_analysis",
                "variant_calling",
                "population_statistics",
            ],
            "description": "Type of analysis to perform",
        },
        "chromosomes": {
            "allowed": [f"chr{i}" for i in range(1, 23)] + ["chrX", "chrY"],
            "required": False,
            "description": "Chromosomes to analyze (1-22, X, Y)",
        },
        "variant_type": {
            "allowed": ["all", "deleterious", "rare", "common"],
            "default": "all",
            "description": "Filter variants by frequency/impact",
        },
    },
    optimization_strategies=[
        "selective_data_extraction",
        "parallelism_autotune",
        "memory_auto_scale",
        "skip_quality_control_on_trusted_data",
    ],
)
