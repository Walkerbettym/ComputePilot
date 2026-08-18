可以。下面我给你一份可以直接拿来当 **开发指导文档 / 项目 Roadmap** 的方案。

我会刻意把它设计成：

> **先做一个真正能用的软件 → 再加入 Agent → 再加入 Scientific Computing → 最后自然长出研究问题。**

而不是一开始就追求“AI Scientist”。

# Scientific Workflow Agent — 项目设计方案

## 0. 项目定位

**项目暂名：`SciFlow`**

一句话：

> **SciFlow 是一个面向科学计算的 Agentic Workflow Runtime，让用户通过自然语言生成可验证、可执行、可恢复、可复现的计算工作流。**

核心理念：

```text
Natural Language
       ↓
Scientific Agent
       ↓
Workflow IR / DAG
       ↓
Validation
       ↓
Workflow Runtime
       ↓
Local / Docker / Slurm
       ↓
Artifacts + Provenance
       ↓
Results / Report
```

第一阶段不要追求：

* 自动发现科学定律
* 自动设计复杂实验
* 全自动 AI Scientist
* Multi-Agent
* 自己训练 LLM

第一阶段只解决一个非常明确的问题：

> **让科研人员更可靠地执行计算实验。**

---

# 1. 目标用户

第一版目标用户不要太广。

## Primary User

### 使用 Python / HPC 的研究人员

例如：

* Computational Science
* Computational Physics
* Computational Chemistry
* Bioinformatics
* Machine Learning
* Scientific ML
* Numerical Simulation

典型环境：

```text
Python
Git
Linux
Docker
Slurm
Jupyter
```

---

# 2. 典型使用场景

用户输入：

> 对 Reynolds number 从 100 到 10000 做 50 个参数点的 simulation，每个参数运行 5 次，使用 16 CPU。运行完成后计算误差、生成图，并找出误差最小的参数。

SciFlow：

```text
User
 ↓
Agent
 ↓
Intent
 ↓
Workflow
 ↓
Validation
 ↓
Human Approval
 ↓
Execution
```

生成：

```text
Parameter Generation
        ↓
 ┌──────┼──────┐
 ↓      ↓      ↓
Job 1  Job 2  ... Job 250
 └──────┼──────┘
        ↓
Result Collection
        ↓
Analysis
        ↓
Visualization
        ↓
Report
```

最终：

```text
runs/
└── experiment-2026-08-18/
    ├── workflow.yaml
    ├── config.yaml
    ├── logs/
    ├── raw/
    ├── processed/
    ├── figures/
    ├── metrics.json
    ├── environment.lock
    └── report.md
```

---

# 3. 核心设计原则

这几个原则建议写进 README。

## Principle 1 — Agent ≠ Runtime

这是整个项目最重要的原则。

```text
Agent
负责：
理解
规划
选择
诊断
修复
```

```text
Runtime
负责：
执行
调度
状态
重试
checkpoint
资源
artifact
```

不要：

```text
LLM → 每一步 tool call
```

而应该：

```text
LLM
 ↓
Workflow
 ↓
Deterministic Runtime
```

---

## Principle 2 — Workflow First

Agent 最终必须生成结构化 workflow。

而不是：

```text
LLM → shell command
```

---

## Principle 3 — Everything Reproducible

每一次运行都应该能够回答：

> **这次结果到底是怎么产生的？**

保存：

```text
code
config
workflow
dataset
environment
parameters
logs
results
model version
```

---

## Principle 4 — Human-in-the-loop

高成本操作必须允许人工批准。

例如：

```text
Estimated cost:
$132 / 2,400 GPU minutes

Continue?
[Y/N]
```

---

## Principle 5 — Local First

不要第一版就依赖：

```text
AWS
Kubernetes
Cloud
```

先支持：

```text
Local
Docker
Slurm
```

---

# 4. 总体架构

```text
┌──────────────────────────────────────────┐
│                  CLI / UI                │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│              Agent Layer                 │
│                                          │
│ Intent Parser                            │
│ Planner                                  │
│ Skill Selector                           │
│ Error Diagnoser                          │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│             Workflow Layer               │
│                                          │
│ Workflow Schema                          │
│ DAG                                      │
│ Validator                                │
│ Compiler                                 │
│ Optimizer                                │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│             Runtime Layer                │
│                                          │
│ Scheduler                                │
│ Executor                                 │
│ State Manager                            │
│ Checkpoint                               │
│ Retry                                    │
│ Cache                                    │
└──────────────────┬───────────────────────┘
                   │
       ┌───────────┼──────────────┐
       ▼           ▼              ▼
    Local       Docker         Slurm
       │           │              │
       └───────────┼──────────────┘
                   ▼
┌──────────────────────────────────────────┐
│            Artifact Layer                │
│                                          │
│ Data / Model / Figure / Log / Report     │
│ Provenance                               │
└──────────────────────────────────────────┘
```

---

# 5. Repository 结构

建议直接按照这个开始：

```text
sciflow/
│
├── README.md
├── LICENSE
├── pyproject.toml
│
├── docs/
│   ├── architecture.md
│   ├── workflow.md
│   ├── runtime.md
│   ├── agent.md
│   └── contributing.md
│
├── sciflow/
│   │
│   ├── agent/
│   │   ├── planner.py
│   │   ├── intent.py
│   │   ├── selector.py
│   │   └── diagnosis.py
│   │
│   ├── workflow/
│   │   ├── schema.py
│   │   ├── dag.py
│   │   ├── validator.py
│   │   └── compiler.py
│   │
│   ├── runtime/
│   │   ├── engine.py
│   │   ├── scheduler.py
│   │   ├── executor.py
│   │   ├── state.py
│   │   ├── checkpoint.py
│   │   ├── retry.py
│   │   └── cache.py
│   │
│   ├── executors/
│   │   ├── local.py
│   │   ├── docker.py
│   │   └── slurm.py
│   │
│   ├── skills/
│   │   ├── base.py
│   │   ├── python.py
│   │   └── slurm.py
│   │
│   ├── artifacts/
│   │   ├── store.py
│   │   └── provenance.py
│   │
│   ├── models/
│   │   ├── workflow.py
│   │   ├── task.py
│   │   ├── run.py
│   │   └── artifact.py
│   │
│   └── cli/
│       └── main.py
│
├── examples/
│   ├── hello_world/
│   ├── parameter_sweep/
│   ├── ml_training/
│   └── slurm/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── examples/
│
└── scripts/
```

---

# 6. 第一核心模块：Workflow Schema

这是整个系统的基础。

建议先定义一个简单 DSL。

例如：

```yaml
name: parameter_sweep

inputs:
  start: 100
  end: 10000
  num_points: 50

tasks:

  - id: generate
    type: python
    command: generate.py

  - id: simulate
    type: python
    command: simulate.py
    depends_on:
      - generate

  - id: analyze
    type: python
    command: analyze.py
    depends_on:
      - simulate

  - id: visualize
    type: python
    command: plot.py
    depends_on:
      - analyze
```

对应：

```text
generate
    ↓
simulate
    ↓
analyze
    ↓
visualize
```

---

# 7. Task Model

每一个 Task 至少包含：

```text
Task
├── id
├── type
├── command
├── inputs
├── outputs
├── dependencies
├── resources
├── environment
├── retry_policy
└── timeout
```

例如：

```yaml
id: simulation

type: python

command: python simulate.py

inputs:
  - params.json

outputs:
  - results.csv

resources:
  cpu: 16
  memory: 32GB

retry:
  max_attempts: 3

timeout: 2h
```

---

# 8. Workflow Validation

这是非常重要的。

Agent 生成 workflow 后：

```text
LLM
 ↓
Workflow
 ↓
Validator
```

Validator 检查：

### Structural

```text
DAG 是否有 cycle？
dependency 是否存在？
task id 是否重复？
```

### Resource

```text
CPU 是否合理？
GPU 是否存在？
memory 是否合理？
```

### Input/Output

```text
task B 是否依赖 task A 的 output？
```

### Scientific

未来可以：

```text
是否设置 random seed？
是否做 convergence check？
是否保存 metadata？
```

---

# 9. Runtime

Runtime 是真正执行 workflow 的地方。

核心：

```text
Workflow
 ↓
Scheduler
 ↓
Ready Tasks
 ↓
Executor
 ↓
State
```

状态：

```text
PENDING
RUNNING
SUCCESS
FAILED
CANCELLED
SKIPPED
RETRYING
```

---

# 10. Scheduler

例如：

```text
A
├── B
├── C
└── D
      ↓
      E
```

Runtime 应该知道：

```text
A → complete

B ready
C ready
D ready

E waiting
```

B/C/D 可以并行。

所以：

> **DAG + concurrency**

是 Runtime 的核心。

---

# 11. Executor

统一接口：

```text
Executor
├── LocalExecutor
├── DockerExecutor
└── SlurmExecutor
```

例如：

```text
executor.run(task)
executor.status(task)
executor.cancel(task)
```

这样上层不关心：

```text
Local
Docker
Slurm
```

---

# 12. Checkpoint

每一个 task 完成后：

```text
checkpoint
```

记录：

```json
{
  "task_id": "simulation_42",
  "status": "success",
  "start_time": "...",
  "end_time": "...",
  "exit_code": 0,
  "inputs": [...],
  "outputs": [...]
}
```

系统崩溃：

```text
resume
```

从：

```text
last successful task
```

继续。

---

# 13. Artifact Store

建议第一版：

```text
filesystem
```

以后：

```text
S3
MinIO
HuggingFace
```

Artifact：

```text
Artifact
├── path
├── type
├── checksum
├── producer
├── created_at
└── metadata
```

例如：

```text
results.csv
    ↓
SHA256
    ↓
abc123...
```

这样可以判断：

> 这个文件有没有变化？

---

# 14. Provenance

这个功能我建议你从第一版就设计进去。

记录：

```text
Experiment
   ↓
Workflow
   ↓
Task
   ↓
Code version
   ↓
Input
   ↓
Environment
   ↓
Output
```

最终形成 provenance graph：

```text
dataset
   ↓
preprocess
   ↓
simulation
   ↓
results
   ↓
analysis
   ↓
figure
```

这是以后往科研方向扩展的重要基础。

---

# 15. Agent Layer

等 Runtime 跑通后再做。

Agent 负责：

```text
User Request
 ↓
Intent Extraction
 ↓
Skill Retrieval
 ↓
Planning
 ↓
Workflow Generation
 ↓
Validation
 ↓
Human Approval
```

---

# 16. Intent Schema

例如用户：

> 用 32 个 CPU 跑这个 Python simulation，参数从 1 到 100，每 2 一个点。

Agent 不应该直接生成 shell。

先转换：

```json
{
  "task": "parameter_sweep",
  "parameters": {
    "name": "x",
    "start": 1,
    "end": 100,
    "step": 2
  },
  "resources": {
    "cpu": 32
  }
}
```

然后：

```text
Intent
 ↓
Workflow Compiler
 ↓
DAG
```

这个设计非常重要。

---

# 17. Scientific Skills

Skill 是 Agent 理解科学工具的方式。

例如：

```text
skills/
└── slurm/
    ├── skill.yaml
    ├── docs.md
    └── templates/
```

Skill：

```yaml
name: slurm

capabilities:
  - submit_job
  - monitor_job
  - cancel_job

constraints:
  max_walltime: 72h

error_handling:
  OOM:
    action: increase_memory

  TIMEOUT:
    action: inspect_progress
```

未来：

```text
OpenFOAM Skill
LAMMPS Skill
GROMACS Skill
PyTorch Skill
```

---

# 18. Tool / Skill Retrieval

如果系统有：

```text
1000 tools
100 skills
```

Agent 不应该全部加载。

流程：

```text
User Query
 ↓
Retriever
 ↓
Relevant Skills
 ↓
Relevant Tools
 ↓
Agent
```

这是 RAG 在这个项目里的正确位置。

---

# 19. Agent Failure Recovery

这是后期最值得做的部分之一。

例如：

```text
Task
 ↓
Slurm
 ↓
FAILED
```

Agent 获取：

```text
exit code
stderr
resource usage
logs
```

然后：

```text
Failure Diagnosis
       ↓
┌──────┼────────┐
↓      ↓        ↓
Retry  Repair   Human
```

例如：

```text
OOM
 ↓
increase memory
 ↓
validate
 ↓
retry
```

但：

```text
invalid scientific input
 ↓
STOP
 ↓
Human approval
```

---

# 20. Human Approval

建立：

```text
Policy Engine
```

例如：

```yaml
policies:

  max_cpu: 128

  max_gpu: 8

  max_cost: 100

  require_approval_if:
    - gpu_hours > 100
    - task_count > 1000
```

Agent：

```text
I estimate:

1000 jobs
128 CPU each
~20 hours

Continue?
```

---

# 21. UI 不要一开始做复杂

第一版：

```bash
sciflow init
```

```bash
sciflow plan "run parameter sweep..."
```

```bash
sciflow validate workflow.yaml
```

```bash
sciflow run workflow.yaml
```

```bash
sciflow status
```

```bash
sciflow logs task-42
```

```bash
sciflow resume run-001
```

```bash
sciflow artifacts run-001
```

CLI 足够了。

---

# 22. 第二阶段再做 Web UI

可以做：

```text
┌─────────────────────────────────────┐
│ Experiment #1024                    │
├─────────────────────────────────────┤
│                                     │
│ generate       ✓                    │
│       ↓                             │
│ simulation     ███████░░ 73%        │
│       ↓                             │
│ analysis       pending              │
│       ↓                             │
│ report         pending              │
│                                     │
├─────────────────────────────────────┤
│ CPU: 512 cores                      │
│ Runtime: 02:31:20                   │
│ Failed tasks: 3                     │
└─────────────────────────────────────┘
```

后期再做。

---

# 23. 推荐技术栈

我会选择：

### Core

**Python**

因为科学计算生态最重要。

### Workflow

自己定义 DAG，不要第一版严重依赖 LangGraph。

### Validation

Pydantic

### CLI

Typer

### Async

asyncio

### Persistence

SQLite

### Artifact

Local filesystem

### Container

Docker

### HPC

Slurm

### Agent

OpenAI-compatible API

这样用户可以选择不同模型。

### UI

后期：

```text
FastAPI
React / Next.js
```

---

# 24. 不要把项目绑死在某个 LLM

定义：

```python
class LLMProvider:
    def generate(...)
    def structured_output(...)
```

然后支持：

```text
OpenAI
Anthropic
Gemini
local model
vLLM
Ollama
```

你的项目价值应该在：

```text
Workflow
Runtime
Scientific Infrastructure
```

而不是：

```text
某一个模型
```

---

# 25. MVP 开发顺序

这是我认为最重要的一部分。

## Phase 0 — Design

**1 周**

完成：

```text
Architecture
Workflow Schema
Task Schema
Runtime interface
Executor interface
```

---

# Phase 1 — Workflow Engine

**2–3 周**

实现：

```text
DAG
Scheduler
Executor
State
CLI
```

做到：

```bash
sciflow run workflow.yaml
```

可以真的运行。

---

# Phase 2 — Reproducibility

**1–2 周**

加入：

```text
Checkpoint
Artifact
Provenance
Run metadata
```

做到：

```bash
sciflow resume run-001
```

---

# Phase 3 — Docker / Slurm

**2–3 周**

加入：

```text
LocalExecutor
DockerExecutor
SlurmExecutor
```

这是第一个真正有价值的 release。

---

# Phase 4 — Agent

**2–3 周**

加入：

```text
Intent
Planner
Workflow Generator
Validator
```

做到：

```bash
sciflow plan "run..."
```

自动生成：

```text
workflow.yaml
```

---

# Phase 5 — Scientific Skills

**2–3 周**

先：

```text
Python
Slurm
```

再：

```text
OpenFOAM
LAMMPS
GROMACS
```

---

# Phase 6 — Recovery Agent

**3–4 周**

加入：

```text
Failure Diagnosis
Retry
Repair
Human Approval
```

这个阶段开始有研究味道。

---

# Phase 7 — UI

最后再做：

```text
Experiment Dashboard
Workflow Graph
Logs
Artifacts
```

---

# 26. 第一版成功标准

我建议你不要用：

> “代码写完了”

作为完成标准。

而是定义一个真实 Demo：

### Demo 1

用户：

> Run a parameter sweep from 1 to 100 with 50 points.

系统：

```text
Generate workflow
 ↓
Run 50 jobs
 ↓
Collect results
 ↓
Analyze
 ↓
Plot
```

---

### Demo 2

模拟一个失败：

```text
job 17
 ↓
OOM
```

系统：

```text
detect
 ↓
diagnose
 ↓
increase memory
 ↓
retry
 ↓
success
```

---

### Demo 3

中途关闭 Runtime：

```text
job 1 ✓
job 2 ✓
job 3 ✓
job 4 running
```

重新启动：

```text
sciflow resume
```

继续执行。

---

### Demo 4

修改代码：

```text
git commit A
```

运行：

```text
experiment A
```

然后：

```text
git commit B
```

运行：

```text
experiment B
```

系统能够明确知道：

```text
A ≠ B
```

---

# 27. 项目的核心指标

你不是 benchmark 项目，但仍然需要工程指标。

### Reliability

```text
workflow success rate
recovery success rate
```

### Performance

```text
scheduler overhead
workflow startup time
```

### Cost

```text
LLM token usage
LLM calls
compute utilization
```

### Reproducibility

```text
same workflow
same environment
same input
→ same result
```

### Developer Experience

```text
time to create workflow
lines of configuration
```

---

# 28. 未来的研究问题

这部分是你未来申请 PhD 最重要的。

项目跑起来以后，你会自然产生研究问题。

---

## Research A

### LLM → Workflow Translation

> 如何把自然语言科学意图可靠地转换成 executable DAG？

---

## Research B

### Workflow Optimization

比如：

```text
A → B → C
```

是否可以：

```text
A
├── B
└── C
```

并行化？

Agent / compiler 可以自动优化 workflow。

---

## Research C

### Resource-Aware Planning

Agent 不只是：

> “做什么？”

还要：

> “用多少资源做？”

```text
accuracy
vs
compute cost
```

---

## Research D

### Failure-Aware Agents

```text
failure
 ↓
diagnosis
 ↓
repair
 ↓
validation
 ↓
resume
```

这是非常有研究潜力的。

---

## Research E

### Deterministic Runtime + LLM

研究：

> 什么任务应该由 LLM 决策？什么任务应该由 deterministic system 执行？

这个我尤其推荐。

---

# 29. 项目的长期架构

最终可以变成：

```text
                       User
                         │
                         ▼
                ┌─────────────────┐
                │ Scientific Agent│
                └────────┬────────┘
                         │
                  Intent / Plan
                         │
                         ▼
                ┌─────────────────┐
                │ Workflow Compiler│
                └────────┬────────┘
                         │
                      Workflow IR
                         │
                         ▼
                ┌─────────────────┐
                │ Policy / Verify │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Workflow Runtime│
                └────────┬────────┘
                         │
         ┌───────────────┼────────────────┐
         ▼               ▼                ▼
       Local            Docker           HPC
         │               │                │
         └───────────────┼────────────────┘
                         ▼
                ┌─────────────────┐
                │ Artifact Store  │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Provenance Graph│
                └────────┬────────┘
                         │
                         ▼
                    Experiment
```

---

# 30. 我建议你把项目定位成三个关键词

不要宣传成：

> AI Scientist

而是：

# **Agent + Workflow + Reproducibility**

甚至 README 第一行可以是：

> **SciFlow is an open-source agentic workflow runtime for reproducible scientific computing.**

然后三个核心能力：

```text
Understand
    ↓
Plan

Execute
    ↓
Reliable Runtime

Reproduce
    ↓
Artifacts + Provenance
```

---

# 31. 最终的 v0.1 应该长什么样？

我建议你给自己一个非常明确的终点：

```text
$ sciflow plan \
  "Run my simulation with x from 1 to 100,
   use 16 CPUs, analyze the results and
   generate a plot."
```

输出：

```text
Workflow generated:

1. generate_parameters
2. run_simulation [50 parallel jobs]
3. collect_results
4. analyze
5. visualize

Estimated resources:
CPU: 800 core-hours
Runtime: ~2h

Approve? [y/N]
```

然后：

```text
$ sciflow run workflow.yaml
```

运行：

```text
generate_parameters       ✓
simulation 01             ✓
simulation 02             ✓
...
simulation 37             ✗ OOM
...
```

Agent：

```text
Detected failure:

simulation_37
Cause: Out Of Memory

Proposed action:
memory 8GB → 16GB

Approve retry? [Y/n]
```

然后：

```text
simulation_37             ✓
collect_results            ✓
analysis                   ✓
visualization              ✓
```

最后：

```text
Run completed.

Artifacts:
  results.csv
  metrics.json
  figure.png
  report.md

Reproducibility manifest:
  workflow: sha256:...
  code: abc123
  environment: ...
  data: ...
```

**如果你能把这一条完整链路做出来，这个项目就已经非常像样了。**

---

# 32. 最后给你一个现实的 12 周路线

| 周  | 目标                               |
| -- | -------------------------------- |
| 1  | Workflow DSL + Architecture      |
| 2  | DAG + Task Model                 |
| 3  | Local Executor                   |
| 4  | Scheduler + Parallel Execution   |
| 5  | State + Checkpoint               |
| 6  | Artifact + Provenance            |
| 7  | Docker Executor                  |
| 8  | Slurm Executor                   |
| 9  | Agent Intent + Planner           |
| 10 | Workflow Generation + Validation |
| 11 | Failure Diagnosis + Retry        |
| 12 | Demo + Documentation + v0.1      |

**12 周后不要追求 100 个 feature。**

你只需要让一个完整故事跑通：

```text
Natural Language
       ↓
Agent
       ↓
Workflow
       ↓
Validation
       ↓
HPC
       ↓
Failure
       ↓
Recovery
       ↓
Results
       ↓
Reproducible Experiment
```

这就是你的 **North Star Demo**。

---

## 最重要的一点

如果你真准备把它作为未来申请 PhD 的长期项目，我建议你把项目从第一天就分成两个层次：

```text
┌──────────────────────────────────┐
│       Scientific Workflow        │
│          Infrastructure          │
│                                  │
│ DAG / Runtime / Slurm / Artifact │
│ Checkpoint / Provenance          │
└────────────────┬─────────────────┘
                 │
                 │
┌────────────────▼─────────────────┐
│        Agent Intelligence        │
│                                  │
│ Planning                         │
│ Skill Retrieval                  │
│ Workflow Generation              │
│ Failure Diagnosis                │
│ Resource Optimization            │
└──────────────────────────────────┘
```

**下面那层可以不断研究，下面那层产生论文；上面那层保证你的项目即使没有论文也有实际使用价值。**

这正好符合你刚才说的要求：**不是为了论文做 benchmark，而是先做一个真的有用的工程系统，然后从工程问题里长出研究问题。**

如果让我替你正式定 MVP，我会选 **“Python + Docker + Slurm 的 Scientific Workflow Agent”**，暂时不碰 OpenFOAM/GROMACS 等复杂领域工具。这样你可以在没有导师、没有实验室资源的情况下独立把第一版做出来。

