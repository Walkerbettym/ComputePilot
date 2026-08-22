"""Built-in workflow templates for ``cpilot init --template``."""

from __future__ import annotations

HELLO_WORLD = """\
name: hello_world
description: "Minimal ComputePilot workflow"
tasks:
  - id: greet
    command: echo "Hello, ComputePilot!"
    type: shell
"""

PARAMETER_SWEEP = """\
name: parameter_sweep
description: "Fan out a simulation across parameter values with foreach"
params_note: "Run with: cpilot run workflow.yaml --set points=1,2,3"
tasks:
  - id: setup
    command: echo preparing sweep
    type: shell
  - id: simulate
    foreach:
      values: [1, 2, 4, 8]
      as: n
    priority: 5
    command: python simulate.py --points ${n} > result_${n}.json
    type: shell
    depends_on: [setup]
  - id: collect
    command: python collect.py results/*.json > summary.json
    type: shell
    depends_on: [simulate]
"""

ML_PIPELINE = """\
name: ml_pipeline
description: "Train, evaluate, and report on a small model"
tasks:
  - id: train
    command: python train.py --data data.csv --out model.pkl
    type: python
    resources:
      cpu: 4
      memory: 8GB
  - id: evaluate
    command: python evaluate.py --model model.pkl --out metrics.json
    type: python
    depends_on: [train]
  - id: report
    command: python report.py --metrics metrics.json
    type: python
    depends_on: [evaluate]
"""

DOCKER_WORKER = """\
name: docker_worker
description: "Compute inside a pinned container image"
tasks:
  - id: primes
    type: docker
    image: python:3.11-slim
    command: python
    args:
      - "-c"
      - |
        print(sum(n for n in range(2, 2000) if all(n % d for d in range(2, int(n ** .5) + 1))))
    resources:
      cpu: 1
      memory: 512MB
"""

TEMPLATES: dict[str, str] = {
    "hello_world": HELLO_WORLD,
    "parameter_sweep": PARAMETER_SWEEP,
    "ml_pipeline": ML_PIPELINE,
    "docker_worker": DOCKER_WORKER,
}
