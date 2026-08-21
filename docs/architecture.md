# ComputePilot 系统架构

## 四层架构

```
┌────────────────────────────────────────────┐
│              CLI / UI                       │  Typer CLI（computepilot 命令）
├────────────────────────────────────────────┤
│              Agent Layer                    │  意图提取、规划、技能检索、诊断
├────────────────────────────────────────────┤
│           Workflow Layer                    │  Schema 解析、DAG、验证
├────────────────────────────────────────────┤
│           Runtime Layer                     │  引擎、调度、状态、检查点
├────────────────────────────────────────────┤
│           Executor Plugins                  │  Local / Docker / Slurm
├────────────────────────────────────────────┤
│           Artifact Layer                    │  存储、溯源
└────────────────────────────────────────────┘
```

## 依赖方向铁律

```
agent/   →  workflow/  →  models/
         →  runtime/   →  models/  (allowed)
         →  executors/ →  models/  (allowed)

runtime/  →  model/    ✅
runtime/  →  agent/    ❌ 禁止（check_deps.py 强制执行）
```

## 核心模块

### `models/` — 数据模型（Pydantic v2）

| 文件 | 核心类型 |
|---|---|
| `workflow.py` | Workflow, Task, Resources, RetryPolicy, PartialTask |
| `run.py` | Run, RunStatus (8态), TaskStatus (8态) |
| `artifact.py` | Manifest, ArtifactRef |

### `workflow/` — 工作流层

| 文件 | 职责 |
|---|---|
| `schema.py` | YAML ↔ Workflow 序列化 |
| `dag.py` | DAG 拓扑排序、环检测、ready_tasks |
| `validator.py` | 24 条验证规则（结构/资源/I/O/科学） |

### `runtime/` — 运行时

| 文件 | 职责 |
|---|---|
| `engine.py` | 执行引擎（run / resume / 失败处理） |
| `scheduler.py` | 并发控制调度器 |
| `executor.py` | Executor Protocol、TaskResult、Handle |
| `state.py` | SQLite 状态存储（5 张表） |
| `checkpoint.py` | 检查点读写/恢复点发现 |
| `retry.py` | 重试决策 + 退避计算 |

### `executors/` — 执行器

| 执行器 | 隔离级别 | GPU | 备注 |
|---|---|---|---|
| `LocalExecutor` | 进程 | ❌ | 通用子进程 |
| `DockerExecutor` | 容器 | ✅ | 自动清理 |
| `SlurmExecutor` | 作业 | ✅ | sbatch/sacct/scancel |
| `FakeSlurmExecutor` | 内存 | ✅ | CI/测试用 |

### `agent/` — 智能层

| 文件 | 职责 |
|---|---|
| `provider.py` | LLMProvider Protocol + OpenAI 实现 |
| `intent.py` | 自然语言→结构化 Intent |
| `planner.py` | Intent→Workflow 转换 |
| `generator.py` | 高层生成入口（提取+规划） |
| `selector.py` | 技能检索（关键词匹配） |
| `cost.py` | 执行成本估算 |
| `diagnosis.py` | 失败分类与修复建议 |

### `skills/` — 技能系统

通用：python（运行脚本/Notebook）、shell（管道/环境）、docker（容器编排）、slurm（HPC 作业）

领域（v0.5）：population_genetics（1000 Genomes）、openfoam（CFD）、gromacs（分子动力学）、lammps（材料原子尺度）

### `policy/` — 策略引擎

资源上限检查（CPU/GPU/成本）、审批门控

### `artifacts/` — 制品与溯源

ArtifactStore（注册/查询/校验和）、ProvenanceBuilder（manifest.json 生成）

## CLI 命令架构

```
cpilot
├── init       创建项目骨架
├── validate   校验 workflow（24 条规则）
├── dag        可视化依赖图（ascii/mermaid/json）
├── run        执行（Local/Docker/Slurm/K8s；--interactive / --from-session）
├── plan       自然语言→工作流（需 LLM）
├── status     查看运行状态
├── logs       查看事件日志
├── resume     崩溃恢复
├── cancel     取消运行
├── artifacts  列出制品
├── report     生成溯源报告
└── skill      管理技能
```

## 状态机

```
Run: CREATED → VALIDATING → PENDING_APPROVAL → RUNNING → SUCCEEDED/FAILED/CANCELLED
Task: PENDING → READY → RUNNING → SUCCEEDED/FAILED/RETRYING/SKIPPED/CANCELLED
```

## SQLite 持久化

```
runs         — 运行元数据
task_states  — 任务状态（原子事务）
task_events  — 事件日志
artifacts    — 制品注册
approvals    — 审批记录
```