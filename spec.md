# SciFlow — 项目落地规格说明书 (Specification v0.1)

> **来源文档**: `mark.md`(项目设计方案,共 32 节)
> **文档目的**: 将设计方案转化为可指导开发、可验收、可排期的详细规格。本文档是 v0.1(12 周 MVP)的**唯一实现依据**。
> **状态**: Draft v0.1 | **语言**: 中文 | **适用对象**: 开发者 / 审阅者 / 验收者

---

## 0. 文档导读

| 章节 | 内容 | 对开发者的作用 |
| --- | --- | --- |
|| §1–§5 | 定位、哲学、边界、原则 | 理解项目'为什么',防止范围蔓延 |
| §5–§6 | 架构与需求清单 | 全局图景 + 功能优先级 |
| §7–§9 | DSL / 数据模型 / 状态机 | **写代码前必读**,定义所有核心类型 |
| §10–§13 | 模块设计 / 持久化 / 错误处理 | 每个模块的职责与实现契约 |
| §14–§16 | 可复现性 / 技术栈 / 仓库结构 | 工程基座 |
|| §17–§20 | 测试 / 里程碑 / 验收(North Star Demo) / 指标 | 排期与验收依据 |
| §21–§22 | 风险 / 未来研究 | 边界与演进方向 |

**本文档的关键约定**

1. **优先级标记**: `P0` = v0.1 必须完成;`P1` = v0.1 应当完成(若无则 Release 推迟);`P2` = 后续版本。
2. **依赖方向铁律**: `runtime/` **禁止** import `agent/` 或任何 LLM 依赖;`agent/` 只能依赖 `workflow/`、`runtime/`、`models/` 的公开接口。此规则用 CI 检查强制。
3. **验收即测试**: §19 的 4 个 Demo 同时是 `tests/e2e/` 下的自动化测试套件。

---

## 1. 项目概述

### 1.1 项目定位

**项目暂名**: `SciFlow`(可后续更名)

> **SciFlow 是一个面向科学计算的 Agentic Workflow Runtime,让用户通过自然语言生成可验证、可执行、可恢复、可复现的计算工作流。**

README 第一行(建议):

> **SciFlow is an open-source agentic workflow runtime for reproducible scientific computing.**

### 1.2 核心链路(第一版只跑通这一条故事线)

```text
Natural Language → Scientific Agent → Workflow IR / DAG → Validation
→ Human Approval → Workflow Runtime → Local / Docker / Slurm → Artifacts + Provenance → Report
```

### 1.3 项目定位三关键词

```
Agent + Workflow + Reproducibility
  Understand → Plan → Execute(Reliable Runtime)→ Reproduce(Artifacts + Provenance)
```

### 1.4 项目双层次结构(从第一天起保持)

```text
┌──────────────────────────────────┐
│       Scientific Workflow        │   ← 工程层:保证项目有实际使用价值
│          Infrastructure          │
│ DAG / Runtime / Slurm / Artifact │
│ Checkpoint / Provenance          │
└────────────────┬─────────────────┘
                 │
┌────────────────▼─────────────────┐
│        Agent Intelligence        │   ← 研究层:产出论文
│ Planning / Skill Retrieval       │
│ Workflow Generation              │
│ Failure Diagnosis / Resource Opt │
└──────────────────────────────────┘
```

---
### 1.5 核心哲学

以下三条哲学贯穿 v0.1 所有决策,建议写入 README 顶层。

> **哲学一:先做一个真正能用的软件。**
> 再加入 Agent → 再加入 Scientific Computing → 最后自然长出研究问题。
> 不要一开始就追求"AI Scientist"。先解决一个非常明确的问题:**让科研人员更可靠地执行计算实验。**

> **哲学二:不是为了论文做 benchmark,而是先做一个真的有用的工程系统,然后从工程问题里长出研究问题。**
> 项目从第一天起就分成两个层次(§1.4):下面的 Infrastructure 层保证项目即使没有论文也有实际使用价值;
> 上面的 Intelligence 层不断产生研究问题。
> 不要用"代码写完了"作为完成标准——而是定义一个真实 Demo 作为验收标准(§18)。

> **哲学三:Agent ≠ Runtime。**
> 这是整个项目最重要的设计原则(§4 P1)。Agent 负责理解、规划、诊断;Runtime 负责执行、调度、状态、重试、checkpoint、资源、artifact。
> 禁止 LLM → 每一步 tool call 的模式;必须走 LLM → Workflow → Deterministic Runtime 的路径。


## 2. 目标与边界

### 2.1 v0.1 目标

> **让科研人员更可靠地执行计算实验。**

一个明确的 North Star 场景:用户用一句话描述参数扫描实验 → 系统生成可执行工作流 → 批准 → 运行(50 个并行任务)→ 出错自动诊断修复 → 崩溃可恢复 → 产出可复现报告。

### 2.2 v0.1 非目标(明确不做)

| # | 不做 | 原因 |
| --- | --- | --- |
| NG-1 | 自动发现科学定律 / 自动设计复杂实验 | 超出 MVP 范围 |
| NG-2 | 全自动 AI Scientist(无人干预) | 违背 Principle 4 |
| NG-3 | Multi-Agent 系统 | 单 Agent 足够;架构预留 |
| NG-4 | 自训练 / 微调 LLM | 只做推理调用 |
| NG-5 | OpenFOAM / GROMACS / LAMMPS 等复杂领域 Skill | 第二阶段;MVP 只做 python/shell/slurm 通用能力 |
| NG-6 | Web UI / Dashboard | 第二阶段;MVP 只做 CLI |
| NG-7 | 云部署(AWS / Kubernetes) | 违背 Principle 5;架构预留 |
| NG-8 | 分布式运行时(Dask / Ray 做引擎) | MVP 用 asyncio + 多进程;引擎接口预留 |
| NG-9 | 多用户 / 权限系统 / 多租户 | 单机单用户工具 |
| NG-10 | 图形化 workflow 编辑器 | 后续 |

### 2.3 v0.1 边界条件

- 运行环境: Linux / macOS(本地);Linux 集群(Slurm)
- Python ≥ 3.11
- 用户身份: 单用户(CLI 在同一账号下运行)
- 默认工作目录: `sciflow init` 生成的项目目录

---

## 3. 用户与场景

### 3.1 目标用户(第一版收窄)

**Primary User: 使用 Python / HPC 的研究人员**

| 领域 | 典型工具链 |
| --- | --- |
| Computational Science / Physics / Chemistry | Python + NumPy/SciPy + MPI |
| Bioinformatics | Python + Snakemake 经验 |
| Machine Learning / Scientific ML | PyTorch + GPU 集群 |
| Numerical Simulation | Slurm + 作业脚本 |

典型环境: `Python + Git + Linux + Docker + Slurm + Jupyter`

### 3.2 典型使用场景(用于 Demo 与验收)

> 用户输入: "对 Reynolds number 从 100 到 10000 做 50 个参数点的 simulation,每个参数运行 5 次,使用 16 CPU。运行完成后计算误差、生成图,并找出误差最小的参数。"

系统行为(§19 Demo 1 的正式版本):

```text
User → Agent → Intent → Workflow → Validation → Human Approval → Execution
   Parameter Generation
        ↓
   ┌──────┼──────┐
   ↓      ↓      ↓
 Job 1  Job 2 ... Job 250        (50 参数 × 5 次重复 = 250 个作业)
   └──────┼──────┘
        ↓
   Result Collection → Analysis → Visualization → Report
```

产物目录(§12.2 规范):

```text
runs/
└── experiment-2026-08-18/
    ├── workflow.yaml       # 冻结副本(只读)
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

## 4. 设计原则与工程约束

| # | 原则 | 工程约束(强制) |
| --- | --- | --- |
| P1 | **Agent ≠ Runtime** | 1) `sciflow/runtime/` 内**禁止** import `sciflow/agent/` 及 LLM SDK;2) Agent 输出只能是 Workflow 对象,不是 shell;3) Runtime 在无网络、无 API key 环境下可完整工作 |
| P2 | **Workflow First** | 1) 所有执行入口只接受 `workflow.yaml`;2) 禁止 "LLM → shell command" 直接执行路径;3) `sciflow run` 不接收自然语言 |
| P3 | **Everything Reproducible** | 每次 run 必须冻结并记录: code、config、workflow、dataset、environment、parameters、logs、results、model version;缺一不可生成 manifest(§14) |
| P4 | **Human-in-the-loop** | 超过策略阈值(§13.4)的操作必须阻塞等待审批;审批动作写入审计日志 |
| P5 | **Local First** | 默认 executor = Local;Docker / Slurm 是可选插件;零云依赖;CI 全程可在无集群环境运行 |

---

## 5. 系统架构

### 5.1 分层架构

```text
┌──────────────────────────────────────────┐
│                  CLI / UI                 │   sciflow/cli
└──────────────────┬───────────────────────┘
                   ▼
┌──────────────────────────────────────────┐
│              Agent Layer                  │   sciflow/agent   (可有 LLM 依赖)
│ Intent Parser / Planner / Skill Selector  │
│ Workflow Generator / Error Diagnoser      │
└──────────────────┬───────────────────────┘
                   ▼
┌──────────────────────────────────────────┐
│             Workflow Layer                │   sciflow/workflow (纯逻辑,无 LLM)
│ Workflow Schema / DAG / Validator /       │
│ Compiler / Optimizer                      │
└──────────────────┬───────────────────────┘
                   ▼
┌──────────────────────────────────────────┐
│             Runtime Layer                 │   sciflow/runtime  (纯逻辑,无 LLM)
│ Scheduler / Executor / State Manager /    │
│ Checkpoint / Retry / Cache                │
└──────────────────┬───────────────────────┘
                   │
       ┌───────────┼──────────────┐
       ▼           ▼              ▼
    Local       Docker         Slurm          sciflow/executors
       │           │              │
       └───────────┼──────────────┘
                   ▼
┌──────────────────────────────────────────┐
│            Artifact Layer                 │   sciflow/artifacts
│ Data / Model / Figure / Log / Report      │
│ Provenance                                │
└──────────────────────────────────────────┘
```

### 5.2 依赖方向(CI 强制检查)

```text
cli → agent → workflow → runtime → executors → artifacts
                    ↘ models(共享,无依赖) ↗
```

- `models/`: 无任何内部依赖,被所有层引用
- `workflow/`: 可依赖 `models/`;**不得**依赖 runtime/agent
- `runtime/`: 可依赖 `models/`、`workflow/`(只读 schema);**不得**依赖 agent
- `agent/`: 可依赖 workflow/runtime/models
- 检查方式: CI 步骤运行 `scripts/check_deps.py`,解析 import 语句,违反即失败

### 5.3 关键数据流(一次完整运行)

```text
1. user query
2. IntentExtractor → Intent(结构化)
3. SkillRetriever → 相关 skills(≤ top-k)
4. Planner → 步骤列表
5. WorkflowGenerator → workflow.yaml draft
6. Validator → 校验报告(错误/警告)
7. CostEstimator + PolicyEngine → 审批决策
8. Human Approval(CLI Y/N 或 --approve)
9. Runtime: 加载 → 校验 → 调度 → 执行 → checkpoint → artifact 注册
10. 失败 → Diagnoser → 修复建议 → 重试或人工
11. 完成 → manifest.json + report.md
```

---

## 6. 功能需求清单

### 6.1 功能需求(FR)

| ID | 优先级 | 需求 | 对应模块 |
| --- | --- | --- | --- |
| FR-01 | P0 | `sciflow init` 生成项目骨架(目录 + 示例 workflow) | cli |
| FR-02 | P0 | workflow.yaml 解析为强类型模型;解析/校验失败输出具体错误(行号、字段、原因) | workflow/schema |
| FR-03 | P0 | DAG 构建:拓扑排序、环检测、孤立节点检测 | workflow/dag |
| FR-04 | P0 | `sciflow validate` 静态校验:结构 / 资源 / I/O(§8.3) | workflow/validator |
| FR-05 | P0 | LocalExecutor:子进程执行任务,支持并发上限 | executors/local |
| FR-06 | P0 | Scheduler:按依赖就绪调度 + 最大并发控制 | runtime/scheduler |
| FR-07 | P0 | 状态持久化:SQLite(§12.1)+ run 目录(§12.2) | runtime/state |
| FR-08 | P0 | `sciflow status` 实时查看 DAG 与任务状态 | cli/runtime |
| FR-09 | P0 | `sciflow logs <run-id> <task-id> [--tail N]` | cli/runtime |
| FR-10 | P1 | 每任务完成后写 checkpoint;`sciflow resume <run-id>` 从最后一个成功任务继续 | runtime/checkpoint |
| FR-11 | P1 | Artifact 注册:路径、类型、SHA256、生产者、元数据 | artifacts/store |
| FR-12 | P1 | Provenance: manifest.json 生成(§14.2) | artifacts/provenance |
| FR-13 | P1 | `sciflow report <run-id>` 生成 report.md(由 manifest 渲染) | cli/artifacts |
| FR-14 | P1 | DockerExecutor:镜像固定( digest 或 tag+pull)、容器内运行、资源映射 | executors/docker |
| FR-15 | P1 | SlurmExecutor:sbatch 提交、squeue 监控、scancel、分区/节点/墙钟映射 | executors/slurm |
| FR-16 | P1 | 重试策略:max_attempts、backoff、可重试退出码/信号(§13.3) | runtime/retry |
| FR-17 | P2 | `sciflow plan "<自然语言>"` → 生成 workflow.yaml draft + 成本估算 + 审批 | agent |
| FR-18 | P2 | Intent 结构化提取:verb、target、parameters、resources、constraints | agent/intent |
| FR-19 | P2 | Skill 注册 / 检索(§10.6.3):关键词 + 向量检索,top-k 注入 | agent/selector |
| FR-20 | P2 | 失败诊断:规则分类器(OOM/超时/缺文件/语法错误)+ LLM 深度诊断 → 修复建议 | agent/diagnosis |
| FR-21 | P2 | 策略引擎 + 人工审批(§13.4) | policy |
| FR-22 | P2 | 成本估算:资源 × 时长 × 单价表 → 预估金额与资源量 | agent/cost |
| FR-23 | P2 | 任务级缓存:相同输入哈希 + 相同命令哈希 → SKIPPED(复用产物) | runtime/cache |
| FR-24 | P1 | 结构化 JSON 日志(run.log + 每任务日志文件) | runtime/logging |
| FR-25 | P0 | 退出码约定:0 成功 / 1 运行失败 / 2 参数或校验错误 / 3 审批拒绝 / 4 内部错误 | cli |

### 6.2 非功能需求(NFR)

| ID | 类别 | 指标(可测量) | 验证方式 |
| --- | --- | --- | --- |
| NFR-01 | 可靠性 | e2e demo 套件通过率 ≥ 90% | CI 每次运行 |
| NFR-02 | 恢复 | 运行中途 kill 进程 → resume 后不丢已完成任务、不重复执行已完成任务 | Demo 3 自动化测试 |
| NFR-03 | 性能 | 100 任务调度开销 < 100ms;CLI 冷启动 < 1s | `tests/perf/` 基准 |
| NFR-04 | 可复现 | 同 code+config+environment → 关键 artifact SHA256 一致 | Demo 4 |
| NFR-05 | 安全 | 命令以参数数组执行(无 shell 拼接注入);run 目录不做符号链接逃逸;无 sudo 要求 | 单元测试 + 审查 |
| NFR-06 | 兼容 | Python 3.11/3.12;Linux CI + macOS 手动验证 | CI matrix |
| NFR-07 | 可维护 | runtime 零 LLM 依赖;mypy strict 通过;ruff 无错误 | CI |
| NFR-08 | 可观测 | 所有事件结构化日志;任务级日志文件;metrics.json 聚合 | 日志规范测试 |
| NFR-09 | 成本 | 每次 plan 记录 LLM token 用量与调用次数 | plan 元数据 |

---

## 7. Workflow DSL 规范(v0.1)

### 7.1 语法与顶层结构

文件: `workflow.yaml`(UTF-8,YAML 1.2)

```yaml
name: parameter_sweep            # 必填,^[a-z0-9_-]{1,64}$
description: 雷诺数参数扫描      # 可选
version: "0.1.0"                 # 可选,工作流自身版本
schema_version: 1                # 可选,默认 1(DSL 版本,向前兼容依据)

variables:                       # 可选,变量插值 ${variables.x}
  start: 100
  end: 10000
  num_points: 50
  repeats: 5

env:                             # 可选,工作流级环境变量(所有任务继承)
  PYTHONUNBUFFERED: "1"

defaults:                        # 可选,任务字段默认值(任务级覆盖)
  type: python
  resources:
    cpu: 1
    memory: 2GB

tasks:                           # 必填,≥ 1 个
  - id: generate
    type: python
    command: python generate.py ${variables.num_points}
    outputs: [params.json]

  - id: simulate
    type: python
    command: python simulate.py params.json ${variables.start} ${variables.end}
    depends_on: [generate]
    inputs: [params.json]
    outputs: [results.csv]
    resources:
      cpu: 16
      memory: 32GB
    retry:
      max_attempts: 3
    timeout: 2h

  - id: analyze
    type: python
    command: python analyze.py
    depends_on: [simulate]
    inputs: [results.csv]
    outputs: [metrics.json]

  - id: visualize
    type: python
    command: python plot.py
    depends_on: [analyze]
    inputs: [metrics.json]
    outputs: [figure.png]
```

### 7.2 字段参考

#### 顶层字段

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `name` | str | ✓ | 正则 `^[a-z0-9_-]{1,64}$` |
| `description` | str | – | |
| `version` | str | – | semver 风格 |
| `schema_version` | int | – | 默认 1 |
| `variables` | dict[str, str\|int\|float] | – | 值必须 JSON 标量 |
| `env` | dict[str, str] | – | |
| `defaults` | PartialTask | – | 同 Task 字段,均可被任务级覆盖 |
| `tasks` | list[Task] | ✓ | 1..N |

#### Task 字段

| 字段 | 类型 | 必填 | 约束 / 语义 |
| --- | --- | --- | --- |
| `id` | str | ✓ | 正则 `^[a-zA-Z_][a-zA-Z0-9_-]*$`,工作流内唯一 |
| `type` | enum | ✓ | `python` \| `shell` \| `docker` \| `slurm`(见 §7.4) |
| `command` | str | ✓ | 非空;支持 `${variables.x}` 插值 |
| `args` | list[str] | – | 若提供,以数组方式执行(安全) |
| `inputs` | list[str] | – | 相对 run 目录路径 |
| `outputs` | list[str] | – | 相对 run 目录路径;跨任务引用须匹配生产者输出 |
| `depends_on` | list[str] | – | 任务 id;可空(入口任务) |
| `resources` | Resources | – | 见下 |
| `environment` | dict[str,str] | – | 任务级环境变量 |
| `retry` | RetryPolicy | – | 见下 |
| `timeout` | duration | – | 格式: `30s` `10m` `2h` `1d`;超时视为失败(可重试) |
| `checkpoint` | bool | – | 默认 true;false 的任务不可单独断点续跑 |
| `tags` | dict[str,str] | – | 自由标签 |
| `metadata` | dict | – | 自由元数据 |

#### Resources

| 字段 | 类型 | 默认 | 约束 |
| --- | --- | --- | --- |
| `cpu` | int | 1 | ≥ 1;Local 执行时用于并发调度;Slurm 映射 `--cpus-per-task` |
| `memory` | str | `2GB` | 可解析格式 `512MB` `2GB` `4GiB`;Slurm 映射 `--mem` |
| `gpu` | int | 0 | ≥ 0;Slurm 映射 `--gres=gpu:N` |
| `partition` | str | – | Slurm `--partition`;Local 忽略 |
| `walltime` | duration | – | Slurm `--time`;与任务 `timeout` 取较小者生效 |

#### RetryPolicy

| 字段 | 类型 | 默认 | 约束 |
| --- | --- | --- | --- |
| `max_attempts` | int | 1 | 1..10;1 = 不重试 |
| `backoff` | enum | `exponential` | `none` \| `fixed` \| `exponential` |
| `base_delay` | duration | `5s` | `none` 时忽略 |
| `max_delay` | duration | `300s` | 指数退避上限 |
| `retryable_exit_codes` | list[int] | `[1, 2, 137]` | 137 = OOM kill |
| `retryable_signals` | list[str] | `[]` | 如 `SIGKILL` |

### 7.3 变量插值规则

- 语法: `${variables.<key>}`;仅出现在 `command` 与 `args` 中
- 未定义 key → 校验错误 E-008
- 插值结果在任务启动时求值,写入任务环境(便于日志追溯)

### 7.4 Task 类型语义

| type | 执行方式(Local 下) | 说明 |
| --- | --- | --- |
| `python` | `python <command>`(argv 数组) | 默认;可用 `python -m` 形式 |
| `shell` | `bash -c <command>` | 显式 shell;受策略引擎危险命令检查(§13.4) |
| `docker` | `docker run --rm ... <image> <command>` | 需 `resources.image`(见下) |
| `slurm` | `sbatch` 包装脚本 | 需要 Slurm 集群;Local 下报"不支持"并建议 `--executor slurm` |

> `docker` 类型额外字段: `image: <repo:tag|@sha256:...>`(必填)、`volumes: list[str]`(选)。

### 7.5 校验规则与错误码(Validator)

#### 结构校验(Structural)

| 错误码 | 规则 | 级别 |
| --- | --- | --- |
| E-001 | 任务 id 重复 | error |
| E-002 | `depends_on` 引用不存在的任务 id | error |
| E-003 | DAG 存在环(给出环路径) | error |
| E-004 | `command` 为空 | error |
| E-005 | `type` 不在允许集合 | error |
| E-006 | 无任务(`tasks` 为空) | error |
| E-007 | 存在孤立的不可达任务(入口不连通) | warning |
| E-008 | 变量插值引用了未定义变量 | error |
| E-009 | `name` / `id` 不符合正则 | error |

#### 资源校验(Resource)

| 错误码 | 规则 | 级别 |
| --- | --- | --- |
| E-100 | `cpu < 1` 或非整数 | error |
| E-101 | `gpu < 0` 或非整数 | error |
| E-102 | `memory` 格式不可解析 | error |
| E-103 | `timeout` / `walltime` 格式非法或 ≤ 0 | error |
| E-104 | 资源超出策略上限(§13.4,如 max_cpu=128) | error |
| E-105 | `gpu > 0` 但 executor 不支持 GPU | warning(按 executor 能力) |
| E-106 | `max_attempts` 超范围 | error |

#### I/O 校验

| 错误码 | 规则 | 级别 |
| --- | --- | --- |
| E-200 | 任务 B 的 `inputs` 引用了不存在的生产者且文件不在项目根 | error |
| E-201 | 任务 B 依赖任务 A 的 `outputs`,但 `depends_on` 未包含 A | error(提示修复) |
| E-202 | 两个任务声明相同 `outputs` 路径 | error |
| E-203 | `inputs`/`outputs` 路径逃逸 run 目录(`..`) | error |

#### 科学性校验(Scientific,warning 级,可配置升级为 error)

| 错误码 | 规则 |
| --- | --- |
| W-101 | 未设置 random seed(检测不到 `seed`/`random_state` 相关参数) |
| W-102 | 未声明任何收敛性 / 误差检查(检测不到 convergence/error 关键词) |
| W-103 | 工作流无 `env` 或 `environment.lock` 建议(可复现性提示) |
| W-104 | `shell` 类型命令包含危险操作(`rm -rf`、`sudo`、`> /dev/sd*` 等)→ **升级为策略审批触发** |
| W-105 | 任务数 > 100 且未显式设置并发(提示设置 `--max-concurrency`) |

### 7.6 校验输出格式

```text
❌ E-003: cycle detected in DAG: simulate → analyze → simulate
   at tasks: simulate (line 22), analyze (line 30)
⚠️  W-101: no random seed detected; consider setting one for reproducibility
   at task: simulate (line 22)

2 errors, 1 warning. Validation FAILED.
```

- 文本输出用于 CLI;结构化输出 `--json` 供 agent 使用(错误码、位置、消息、修复建议)

---

## 8. 数据模型(Pydantic v2)

所有模型定义于 `sciflow/models/`;字段校验失败信息必须含字段路径。

### 8.1 Workflow

```python
class Workflow(BaseModel):
    id: UUID
    name: str                          # ^[a-z0-9_-]{1,64}$
    description: str | None = None
    version: str = "0.1.0"
    schema_version: int = 1
    source: Path | None = None         # 原始 workflow.yaml 路径
    sha256: str                        # 冻结内容哈希(不含 source)
    variables: dict[str, JSONScalar] = {}
    env: dict[str, str] = {}
    defaults: PartialTask | None = None
    tasks: list[Task]
    created_at: datetime
```

### 8.2 Task

```python
class TaskType(str, Enum):
    PYTHON = "python"
    SHELL = "shell"
    DOCKER = "docker"
    SLURM = "slurm"

class Resources(BaseModel):
    cpu: int = 1
    memory: str = "2GB"                # parseable: 512MB|2GB|4GiB
    gpu: int = 0
    partition: str | None = None
    walltime: timedelta | None = None

class RetryPolicy(BaseModel):
    max_attempts: int = 1
    backoff: Literal["none", "fixed", "exponential"] = "exponential"
    base_delay: timedelta = timedelta(seconds=5)
    max_delay: timedelta = timedelta(seconds=300)
    retryable_exit_codes: list[int] = [1, 2, 137]
    retryable_signals: list[str] = []

class Task(BaseModel):
    id: str                            # 唯一
    type: TaskType
    command: str
    args: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []
    depends_on: list[str] = []
    resources: Resources = Resources()
    environment: dict[str, str] = {}
    image: str | None = None           # 仅 docker
    volumes: list[str] = []            # 仅 docker
    retry_policy: RetryPolicy = RetryPolicy()
    timeout: timedelta | None = None
    checkpoint: bool = True
    tags: dict[str, str] = {}
    metadata: dict[str, Any] = {}
```

### 8.3 Run / TaskState / Artifact

```python
class RunStatus(str, Enum):
    CREATED = "created"                # 已创建,未校验
    VALIDATING = "validating"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    RESUMING = "resuming"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskStatus(str, Enum):
    PENDING = "pending"                # 依赖未就绪
    READY = "ready"                    # 可调度
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"                # 缓存命中或上游失败跳过
    CANCELLED = "cancelled"

class Run(BaseModel):
    id: str                            # experiment-YYYY-MM-DD-NNN
    workflow_id: UUID
    workflow_sha256: str
    status: RunStatus
    executor: str                      # local|docker|slurm
    config: dict[str, Any] = {}        # 冻结 config.yaml
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_dir: Path
    metrics: dict[str, Any] = {}
    manifest: Manifest | None = None

class ArtifactRef(BaseModel):
    task_id: str
    path: str
    type: str                          # data|model|figure|log|report|checkpoint
    checksum: str                      # sha256
    size: int
    created_at: datetime

class Manifest(BaseModel):             # §14.2 结构
    schema_version: int = 1
    run_id: str
    workflow: str                      # sha256
    code: str                          # git commit 或目录哈希
    environment: str                   # lock 文件哈希 + 摘要
    dataset: dict[str, str] = {}       # 输入文件 → sha256
    parameters: dict[str, Any] = {}
    artifacts: list[ArtifactRef]
    task_events: list[TaskEvent]       # 含 checkpoint 摘要
```

### 8.4 Intent / Skill / Diagnosis

```python
class Intent(BaseModel):
    verb: str                          # sweep|train|simulate|analyze|...
    target: str                        # 对象: simulation, model, ...
    parameters: dict[str, Any] = {}    # {name, start, end, step, num_points, repeats, ...}
    resources: Resources = Resources()
    constraints: dict[str, Any] = {}   # walltime, max_cost, accuracy...
    assumptions: list[str] = []        # 显式列出隐含假设,供用户确认

class Skill(BaseModel):
    name: str
    version: str
    description: str
    capabilities: list[str]
    constraints: dict[str, Any] = {}
    resources_defaults: Resources = Resources()
    error_handling: dict[str, ErrorAction] = {}
    templates: list[Path] = []
    docs: Path | None = None

class Diagnosis(BaseModel):
    task_id: str
    cause: str                         # OOM|TIMEOUT|MISSING_INPUT|SYNTAX_ERROR|NODE_FAIL|UNKNOWN
    confidence: float
    explanation: str
    suggested_action: Literal["retry", "repair", "human", "abort"]
    repair: RepairSpec | None = None   # 如 {increase_memory: {factor: 2.0}}
```

---

## 9. 状态机

### 9.1 Run 状态机

```text
CREATED → VALIDATING → PENDING_APPROVAL → RUNNING → SUCCEEDED
                            │                │
                            │ (rejected)     ├──→ FAILED
                            ▼                ├──→ CANCELLED
                        CANCELLED            └──→ RESUMING → RUNNING
```

| 迁移 | 触发条件 |
| --- | --- |
| CREATED → VALIDATING | `run` 命令开始 |
| VALIDATING → PENDING_APPROVAL | 策略引擎判定需要审批(§13.4) |
| VALIDATING → RUNNING | 无需审批或 `--approve` |
| PENDING_APPROVAL → RUNNING | 用户批准(交互 Y / `--approve`) |
| PENDING_APPROVAL → CANCELLED | 用户拒绝;退出码 3 |
| RUNNING → SUCCEEDED | 所有任务终态,无 FAILED |
| RUNNING → FAILED | 存在不可恢复失败任务且无修复路径 |
| RUNNING → CANCELLED | `sciflow cancel` 或 Ctrl-C(二次确认) |
| RUNNING → RESUMING | `sciflow resume` 载入 checkpoint 后回到 RUNNING |

### 9.2 Task 状态机

```text
PENDING → READY → RUNNING → SUCCEEDED
                │           ├──→ FAILED → RETRYING → READY  (重试)
                │           │          (超过 max_attempts → FAILED 终态)
                │           └──→ FAILED → (repair 流程,§13.5)
                └──────────→ SKIPPED    (上游失败/缓存命中)
```

| 迁移 | 触发条件 |
| --- | --- |
| PENDING → READY | 所有依赖 SUCCEEDED(或缓存命中判定完成) |
| READY → RUNNING | Scheduler 分配(受并发上限约束) |
| RUNNING → SUCCEEDED | exit 0 且 outputs 存在 |
| RUNNING → FAILED | 非零退出 / 超时 / executor 错误 |
| FAILED → RETRYING | 失败可重试(§13.3)且 attempts < max_attempts |
| RETRYING → READY | 退避等待结束后重新入队 |
| FAILED → SKIPPED | 上游失败传播:依赖方标记 SKIPPED |
| READY → SKIPPED | 缓存命中(FR-23) |

状态持久化: 每次迁移写入 SQLite(§12.1),任务终态迁移必须原子(事务)。

---

## 10. 模块详细设计

### 10.1 `sciflow/models/` — 数据模型

- `workflow.py` / `task.py` / `run.py` / `artifact.py` / `intent.py` / `skill.py`
- 职责: 仅定义 Pydantic 模型与枚举;提供 `parse_workflow_yaml(path) -> Workflow`(含行号错误收集)
- 约束: 不 import 本包外任何模块

### 10.2 `sciflow/workflow/` — Workflow 层(纯逻辑)

| 文件 | 职责 | 关键接口 |
| --- | --- | --- |
| `schema.py` | YAML ↔ Workflow 模型;行号映射;错误收集 | `load_workflow(path) -> Workflow`;`dump_workflow(wf) -> str` |
| `dag.py` | DAG 构建、拓扑排序、环检测、就绪计算 | `build_dag(workflow) -> DAG`;`topological_order(dag)`;`ready_tasks(dag, completed) -> list[Task]`;`find_cycle(dag) -> list[str]` |
| `validator.py` | §7.5 全部规则 | `validate(workflow, context: ValidateContext) -> ValidationReport` |
| `compiler.py` | 展开变量插值、应用 defaults、产物 → Intent 编译(agent 用) | `compile_intent(intent, skills) -> Workflow` |

**DAG 实现要点**:
- 邻接表表示;任务 id → 节点
- 环检测: Kahn 拓扑排序,剩余节点即环;错误信息包含环路径
- 就绪判定: `ready_tasks` 返回所有依赖已完成且自身未终态的任务

### 10.3 `sciflow/runtime/` — Runtime 层(纯逻辑,零 LLM)

| 文件 | 职责 | 关键接口 |
| --- | --- | --- |
| `engine.py` | 编排总控:加载 → 校验 → 调度循环 → 汇总 | `run(workflow, ctx) -> RunSummary`;`resume(run_id) -> RunSummary` |
| `scheduler.py` | 就绪队列 + 并发上限 + 优先级 | `Scheduler(max_concurrency, queue)`;`schedule(ready_tasks)` |
| `executor.py` | Executor 抽象(见 §10.4) | `Executor` Protocol |
| `state.py` | SQLite 读写;状态机迁移事务 | `StateStore(db_path)`;`transition(run_id, task_id, from, to, **meta)` |
| `checkpoint.py` | 每任务完成写 checkpoint JSON;resume 恢复点计算 | `write_checkpoint(run, task, result)`;`recovery_point(run_id) -> set[task_id]` |
| `retry.py` | 退避计算、可重试判定 | `should_retry(result, policy) -> bool`;`next_delay(attempt, policy) -> timedelta` |
| `cache.py` | 任务指纹(命令+输入哈希)→ 命中则 SKIPPED | `CacheKey(task, input_hashes)`;`hit(key) -> ArtifactRef\|None` |
| `logging.py` | 结构化 JSON 日志;每任务日志文件 | `get_task_logger(run_dir, task_id)` |

**Engine 调度循环(伪代码)**:

```text
queue = Scheduler(max_concurrency=cfg)
completed = load_state(run_id)          # resume 时
while not dag_done:
    ready = dag.ready_tasks(completed)  # 过滤终态/缓存命中
    for t in ready: queue.submit(t)     # 受并发限制
    for done in queue.poll(timeout=1s):
        result = executor.collect(done)
        if cache.hit(key): mark SKIPPED; continue
        if result.ok: write_checkpoint; register_artifacts; completed.add
        elif retry.should_retry: schedule RETRYING (退避后)
        else: fail → engine 决定 FAILED | 交给 agent 修复 (P2)
```

### 10.4 `sciflow/executors/` — Executor 插件

```python
@dataclass
class ExecutorCapability:
    supports_gpu: bool = False
    supports_partition: bool = False
    supports_timeout_kill: bool = True
    isolation: Literal["process", "container", "job"] = "process"
    max_cpu: int = 0                    # 0 = 无限制
    max_memory: str = ""

class Executor(Protocol):
    name: str
    capability: ExecutorCapability

    def validate_task(self, task: Task) -> list[str]: ...       # 任务在此执行器下是否可行
    def submit(self, task: Task, ctx: RunContext) -> Handle: ...
    def status(self, handle: Handle) -> TaskStatus: ...
    def cancel(self, handle: Handle) -> None: ...
    def logs(self, handle: Handle, tail: int = 100) -> str: ...
    def collect(self, handle: Handle) -> TaskResult:            # exit_code, outputs, stats, error
    def resolve_capability(self) -> ExecutorCapability: ...
```

**LocalExecutor**:
- `asyncio.create_subprocess_exec(*argv)`,环境变量注入,`--cwd` 指向任务工作目录
- 并发 = 调度器 max_concurrency;资源映射仅作准入检查(不 cgroup)
- timeout: `asyncio.wait_for` + `kill`

**DockerExecutor**:
- 镜像解析: 优先 digest;tag 时记录 pull 时刻摘要进 manifest
- 命令构造: `docker run --rm -v <run_dir>:/workspace -w /workspace <image> <argv>`
- CPU/内存映射: `--cpus` / `--memory`

**SlurmExecutor**:
- 生成 `sbatch` 包装脚本(任务命令 + 日志重定向 + `scontrol` 上报)
- 提交 → 记录 job id;状态轮询 `sacct`/`squeue`;取消 `scancel`
- 映射: `--cpus-per-task` `--mem` `--gres=gpu:N` `--partition` `--time`
- 退出码与 `REASON` 字段映射到统一错误分类(§13.2)
- **CI 不可用时使用 FakeSlurmExecutor**(同接口,记录式执行),保证单元/集成测试可跑

### 10.5 `sciflow/artifacts/` — Artifact 与 Provenance

| 文件 | 职责 |
| --- | --- |
| `store.py` | 注册 artifact(路径校验 → sha256 → 元数据 → SQLite);列出/查询 |
| `provenance.py` | 构建 provenance 图(节点=artifact/事件,边=produced_by/depends_on);渲染 manifest.json |

Artifact 注册时机: 任务 SUCCEEDED 时扫描声明 `outputs`(缺失 → FAILED),计算 SHA256。

### 10.6 `sciflow/agent/` — Agent 层(可有 LLM 依赖)

| 文件 | 职责 | 关键接口 |
| --- | --- | --- |
| `provider.py` | LLM 抽象与多 Provider 适配 | `LLMProvider` Protocol(见 §10.6.1) |
| `intent.py` | NL → Intent 结构化提取 | `extract_intent(query, skills) -> Intent` |
| `selector.py` | Skill 检索(top-k) | `retrieve(query, skills_index, k) -> list[Skill]` |
| `planner.py` | Intent → 步骤列表 | `plan(intent, skills) -> list[Step]` |
| `generator.py` | 步骤 → workflow.yaml draft(结构化输出 + 自修复 ≤ 3 轮) | `generate_workflow(intent, steps, skills) -> Workflow` |
| `cost.py` | 成本估算 | `estimate(wf, price_table) -> CostEstimate` |
| `diagnosis.py` | 失败分类 + 修复建议 | `diagnose(task, result, logs) -> Diagnosis` |
| `prompts/` | 各步骤 prompt 模板(独立文件,便于迭代) | |

#### 10.6.1 LLMProvider 接口

```python
class LLMProvider(Protocol):
    name: str
    def generate(self, messages: list[Message], *,
                 model: str | None = None,
                 temperature: float = 0.0,
                 max_tokens: int | None = None) -> LLMResponse: ...
    def structured_output(self, messages: list[Message],
                          schema: type[BaseModel], *,
                          model: str | None = None) -> BaseModel: ...
    def usage(self) -> Usage: ...        # tokens, calls(累计,供 FR-22/NFR-09)

# 内置适配器: OpenAIProvider / AnthropicProvider / GeminiProvider /
#             OpenAICompatProvider(vLLM、Ollama、DeepSeek 等)
# 配置: SCIFLOW_LLM_PROVIDER + SCIFLOW_LLM_MODEL + SCIFLOW_LLM_API_KEY(env)
```

原则: 项目价值在 Workflow/Runtime/Scientific Infrastructure,不在模型。禁止任何模块 import 具体 SDK——只依赖 `provider.py` 抽象。

#### 10.6.2 Intent 提取(FR-18)示例

输入: "用 32 个 CPU 跑这个 Python simulation,参数从 1 到 100,每 2 一个点。"

```json
{
  "verb": "parameter_sweep",
  "target": "simulation",
  "parameters": {"name": "x", "start": 1, "end": 100, "step": 2},
  "resources": {"cpu": 32},
  "constraints": {},
  "assumptions": ["命令入口为项目内 simulate 脚本", "参数名为 x"]
}
```

#### 10.6.3 Skill 检索(FR-19)

- 索引: skill.yaml 描述 + docs.md 摘要 → 关键词倒排 + embedding 向量(可选,无 embedding 时仅关键词)
- 流程: `query → retriever → top-k skills(+tools)` → 注入 planner/generator
- v0.1 内置: `python`、`shell`、`slurm`、`docker` 四个基础 skill

### 10.7 `sciflow/skills/` — Skill 包

目录规范:

```text
skills/
└── slurm/
    ├── skill.yaml
    ├── docs.md
    └── templates/
        ├── sbatch.sh.j2
        └── workflow.slurm.yaml.j2
```

skill.yaml 规范(§8.4 Skill 模型的 YAML 对应):

```yaml
name: slurm
version: 0.1.0
description: Slurm 作业提交、监控、取消
capabilities:
  - submit_job
  - monitor_job
  - cancel_job
constraints:
  max_walltime: 72h
  max_nodes: 64
resources_defaults:
  partition: compute
error_handling:
  OUT_OF_MEMORY:
    action: increase_memory
    params: {factor: 2.0}
  TIMEOUT:
    action: inspect_progress
  NODE_FAIL:
    action: resubmit
```

### 10.8 `sciflow/cli/` — CLI(第一版唯一界面)

Typer 实现。命令参考:

```text
sciflow init [dir]                          # FR-01 骨架:workflow.yaml.example + config.yaml + runs/
sciflow plan "<NL 描述>" [--skills ...]      # FR-17 → 输出 draft + 成本估算 + 审批
sciflow validate workflow.yaml [--json]     # FR-04
sciflow run workflow.yaml
        [--executor local|docker|slurm]     # 默认 local
        [--max-concurrency N]               # 默认 4
        [--config config.yaml]
        [--approve]                         # 跳过审批(危险,记审计)
        [--no-cache]
sciflow status [run-id]                     # FR-08;无 run-id 显示最近运行
sciflow logs <run-id> <task-id> [--tail N]  # FR-09
sciflow resume <run-id> [--executor ...]    # FR-10
sciflow cancel <run-id>
sciflow artifacts <run-id> [--type ...]     # FR-11 列表(路径/类型/哈希)
sciflow report <run-id>                     # FR-13
sciflow skill list | add <path>             # FR-19
```

输出风格: `rich` 渲染;状态行含 DAG 缩进与任务状态图标(§22 Web UI 的 CLI 版)。

### 10.9 `sciflow/policy/` — 策略引擎(FR-21)

配置 `config.yaml`:

```yaml
policies:
  max_cpu: 128
  max_gpu: 8
  max_walltime: 72h
  max_estimated_cost_usd: 100
  require_approval_if:
    - gpu_hours > 100
    - task_count > 1000
    - total_cpu_cores > 512
    - partition in [gpu, highmem]
    - command contains "rm -rf"
    - task_type == "shell"
```

交互(示例):

```text
SciFlow estimate:
  1000 jobs × 128 CPU × ~20 hours
  Estimated cost: $132 / 2,400 GPU minutes
Continue? [Y/N]
```

- 审批事件(时间、决策、选项、来源)写入 run 目录 `audit.log`(P4 强制)
- `--approve` 使审批自动化,但同样记录审计

---

## 11. 持久化设计

### 11.1 SQLite Schema(`~/.local/share/sciflow/state.db` 或 `sciflow.db`)

```sql
CREATE TABLE runs (
    id            TEXT PRIMARY KEY,            -- experiment-YYYY-MM-DD-NNN
    workflow_name TEXT NOT NULL,
    workflow_sha256 TEXT NOT NULL,
    status        TEXT NOT NULL,
    executor      TEXT NOT NULL,
    config_json   TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);

CREATE TABLE task_states (
    run_id    TEXT NOT NULL REFERENCES runs(id),
    task_id   TEXT NOT NULL,
    status    TEXT NOT NULL,
    attempt   INTEGER NOT NULL DEFAULT 0,
    exit_code INTEGER,
    error     TEXT,
    start_time TEXT,
    end_time   TEXT,
    PRIMARY KEY (run_id, task_id)
);

CREATE TABLE task_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    TEXT NOT NULL REFERENCES runs(id),
    task_id   TEXT NOT NULL,
    event     TEXT NOT NULL,                   -- submitted|running|succeeded|failed|retrying|skipped|cancelled
    at        TEXT NOT NULL,
    payload   TEXT                             -- JSON(exit_code, error, stats)
);

CREATE TABLE artifacts (
    id         TEXT PRIMARY KEY,               -- sha256 前 16 位 + 序号
    run_id     TEXT NOT NULL REFERENCES runs(id),
    task_id    TEXT,
    path       TEXT NOT NULL,                  -- 相对 run_dir
    type       TEXT NOT NULL,
    checksum   TEXT NOT NULL,                  -- sha256
    size       INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE approvals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL REFERENCES runs(id),
    decision   TEXT NOT NULL,                  -- approved|rejected
    reason     TEXT,
    by         TEXT NOT NULL DEFAULT 'user',
    at         TEXT NOT NULL,
    options_json TEXT
);
```

迁移约束: `transition()` 必须单事务写 `task_states` + `task_events`,防止状态不一致。

### 11.2 Run 目录规范(`runs/<run-id>/`)

```text
runs/experiment-2026-08-18-001/
├── workflow.yaml            # 冻结副本(只读,chmod 444)
├── workflow.sha256
├── config.yaml              # 冻结运行配置(含 executor、并发、策略)
├── environment.lock         # pip freeze / conda env export / 容器 digest
├── manifest.json            # §14.2 完整 provenance
├── state.db                 # 本 run 状态库(或共享库按 run_id 过滤)
├── audit.log                # 审批与关键事件
├── logs/
│   ├── run.log              # 结构化 JSONL
│   └── task-<id>.log        # 每任务 stdout+stderr
├── checkpoints/
│   └── task-<id>.json       # §12 checkpoint 内容
├── raw/                     # 任务原始输出挂载点
├── processed/
├── figures/
├── metrics.json             # 运行指标聚合(耗时、重试数、资源用量)
└── report.md                # report 命令产物
```

### 11.3 Checkpoint 内容(FR-10)

```json
{
  "task_id": "simulation_42",
  "status": "success",
  "attempt": 2,
  "start_time": "2026-08-18T10:00:00Z",
  "end_time": "2026-08-18T10:35:12Z",
  "exit_code": 0,
  "inputs": ["params.json"],
  "outputs": ["results.csv"],
  "output_checksums": {"results.csv": "abc123..."},
  "executor": "local",
  "resource_usage": {"cpu_pct": 3200, "max_rss_mb": 6144}
}
```

`resume` 语义: 从"最后一个成功任务"之后继续;checkpoint=false 的任务失败时,其下游视为不可恢复(需整段重跑)。

---

## 12. 可复现性保障(Principle 3)

### 12.1 冻结清单(每次 run 强制)

| 项目 | 来源 | 记录方式 |
| --- | --- | --- |
| code | 项目目录 git 仓库 | `git rev-parse HEAD`;无 git 时对入口脚本目录递归 sha256 |
| config | config.yaml | 复制到 run 目录 |
| workflow | 运行时工作流对象 | 序列化 + sha256 |
| dataset/inputs | 输入文件清单 | 逐个 sha256 |
| environment | 激活环境 | `pip freeze` / conda list / 容器 digest;存 `environment.lock` |
| parameters | 插值后变量 | manifest.parameters |
| logs / results | 运行时产物 | artifacts 注册 + 日志文件 |

### 12.2 manifest.json 结构

```json
{
  "schema_version": 1,
  "run_id": "experiment-2026-08-18-001",
  "workflow": {"sha256": "a1b2...", "name": "parameter_sweep"},
  "code": {"type": "git", "commit": "abc123...", "dirty": false},
  "environment": {"type": "pip", "lock_sha256": "f0e1..."},
  "dataset": {"params.json": "sha256:...", "input.dat": "sha256:..."},
  "parameters": {"start": 100, "end": 10000, "num_points": 50, "repeats": 5},
  "artifacts": [
    {"task_id": "simulate_0001", "path": "results.csv", "checksum": "...", "type": "data"}
  ],
  "task_events": [
    {"task_id": "simulate_0001", "attempt": 1, "status": "succeeded", "duration_s": 2112}
  ]
}
```

### 12.3 可复现性验证命令(DevOps 用)

```text
sciflow report <run-id>          # 渲染 manifest → report.md
sciflow verify <run-id>          # 重新校验所有 artifact sha256 是否仍一致
```

---

## 13. 错误处理与恢复

### 13.1 失败信息采集(TaskResult)

```python
@dataclass
class TaskResult:
    task_id: str
    ok: bool
    exit_code: int | None
    signal: str | None
    stdout_tail: str
    stderr_tail: str
    resource_usage: ResourceUsage | None
    error: str | None
    outputs: dict[str, str]          # path → sha256
```

### 13.2 失败分类表(Diagnoser 规则层)

| 分类 | 判定特征 | 默认动作(可被 skill.error_handling 覆盖) |
| --- | --- | --- |
| `OOM` | exit 137 / stderr 含 "Killed" / docker OOMKilled / slurm REASON=OUT_OF_MEMORY | repair: memory × 2 → retry(≤ 2 次) |
| `TIMEOUT` | 超时终止 / slurm REASON=TIMEOUT | repair: walltime × 2 + inspect_progress → retry 或 human |
| `MISSING_INPUT` | stderr 含 FileNotFoundError / slurm REASON=BAD_EXTRA_NODES | repair: 检查生产者任务是否成功 → 重跑生产者或 human |
| `SYNTAX_ERROR` | stderr 含 SyntaxError / ModuleNotFoundError / 导入错误 | human(代码问题,agent 不自动改代码) |
| `NODE_FAIL` | slurm REASON=NODE_FAIL / NODE_FAILURE | retry(不修资源) |
| `CANCELLED` | scancel / SIGTERM | 终态,不重试 |
| `UNKNOWN` | 其他 | human |

### 13.3 重试语义(FR-16)

- 判定: `exit_code ∈ retryable_exit_codes` 或 `signal ∈ retryable_signals` 且 `attempt < max_attempts`
- 退避: `delay = min(base_delay * 2^attempt, max_delay)`(exponential);`fixed` 恒为 base_delay
- 每次重试: attempt+1 写入 task_events;checkpoint 记录 attempt
- 重试**不**重新执行缓存命中的上游;下游任务在失败任务成功后正常调度

### 13.4 人工审批与策略引擎(FR-21, Principle 4)

- 触发点: run 前(整体)+ 每次 repair 动作前(§13.5)
- 审批门槛: `require_approval_if` 任一命中 → 状态 PENDING_APPROVAL
- 所有审批进 `approvals` 表 + `audit.log`(不可省略)
- `--approve` 仅跳过交互,不跳过审计

### 13.5 Agent 修复管线(P2, FR-20)

```text
Task FAILED
   ↓
collect TaskResult(exit code, stderr, resource usage, logs)
   ↓
RuleClassifier → 候选分类(§13.2)
   ↓
LLM Diagnosis(仅当规则置信度 < 0.8 或 repair 参数需要决策)
   ↓
Diagnosis(cause, confidence, suggested_action, repair)
   ↓
action = retry      → 按 §13.3 重试
action = repair     → 生成 RepairSpec(memory×2 等)→ 审批 → 修改任务资源 → 重试
action = human      → 停止,输出诊断报告,等待人工
action = abort      → run FAILED,生成完整失败报告
```

**边界**: Agent 不修改用户代码;只调整资源、重试、调度参数。代码级修复一律交 human。

---

## 14. 技术栈与依赖

### 14.1 选型表(遵循 mark.md §23,补充版本与理由)

| 领域 | 选择 | 版本基线 | 理由 |
| --- | --- | --- | --- |
| 语言 | Python | ≥ 3.11 | 科学计算生态;目标用户语言 |
| 包管理 | uv | 最新稳定 | 快、锁文件可靠 |
| 类型模型 | Pydantic | v2.x | DSL 校验、结构化输出 schema |
| CLI | Typer | 最新 | 类型安全、子命令 |
| 异步 | asyncio(stdlib) | – | 无重依赖 |
| 持久化 | SQLite(stdlib `sqlite3`) | – | 单用户足够;避免 ORM 依赖 |
| 日志 | stdlib logging + JSON formatter | – | 可观测性 |
| 渲染 | rich | 最新 | CLI 状态界面 |
| HTTP | httpx | 最新 | LLM API 调用 |
| YAML | PyYAML | 最新 | |
| 容器 | docker CLI(子进程) | – | v0.1 不引入 docker SDK |
| HPC | Slurm 客户端命令 | – | sbatch/sacct/scancel |
| 测试 | pytest + pytest-asyncio | 最新 | |
| Lint/类型 | ruff + mypy | 最新 | mypy strict |
| 打包 | hatchling(setuptools 亦可) | – | |

### 14.2 依赖分层

```text
运行时最小依赖(无 LLM):  pydantic, typer, rich, pyyaml, httpx(仅 agent 用,可延迟导入)
开发依赖:               pytest, pytest-asyncio, ruff, mypy, uv
```

`runtime/` 的 import 集合必须 ⊆ {stdlib, pydantic, pyyaml}——CI 检查。

### 14.3 LLM 配置(不绑定模型)

```text
SCIFFLOW_LLM_PROVIDER=openai|anthropic|gemini|openai_compat
SCIFFLOW_LLM_MODEL=gpt-4o-mini|claude-...|...
SCIFFLOW_LLM_API_KEY=...
SCIFFLOW_LLM_BASE_URL=https://...            # openai_compat(vLLM/Ollama/DeepSeek)
```

---

## 15. 仓库结构

```text
sciflow/
├── README.md                       # 定位、三关键词、快速开始、4 个 Demo 截图区
├── LICENSE                         # 建议 MIT 或 Apache-2.0
├── pyproject.toml
├── .github/workflows/ci.yml        # §16.4
│
├── docs/
│   ├── architecture.md             # 本文档 §5 的展开
│   ├── workflow.md                 # DSL 规范(§7 的展开,用户手册)
│   ├── runtime.md                  # 运行时内部设计
│   ├── agent.md                    # Agent 设计 + prompt 说明
│   └── contributing.md
│
├── sciflow/
│   ├── __init__.py                 # __version__
│   ├── models/                     # §8
│   │   ├── workflow.py  task.py  run.py  artifact.py  intent.py  skill.py
│   ├── workflow/
│   │   ├── schema.py  dag.py  validator.py  compiler.py
│   ├── runtime/
│   │   ├── engine.py  scheduler.py  executor.py  state.py
│   │   ├── checkpoint.py  retry.py  cache.py  logging.py
│   ├── executors/
│   │   ├── base.py  local.py  docker.py  slurm.py  fake_slurm.py
│   ├── skills/
│   │   ├── base.py  python.py  shell.py  slurm.py  docker.py
│   │   └── registry.py             # skill 扫描/加载
│   ├── artifacts/
│   │   ├── store.py  provenance.py
│   ├── policy/
│   │   └── engine.py
│   ├── agent/
│   │   ├── provider.py  intent.py  selector.py  planner.py
│   │   ├── generator.py  cost.py  diagnosis.py
│   │   └── prompts/                # *.j2 模板
│   └── cli/
│       ├── main.py                 # Typer app
│       ├── commands/
│       │   ├── init.py  plan.py  validate.py  run.py
│       │   ├── status.py  logs.py  resume.py  cancel.py
│       │   ├── artifacts.py  report.py  skill.py
│       └── ui.py                   # rich 渲染
│
├── examples/
│   ├── hello_world/                # 单任务 hello
│   ├── parameter_sweep/            # §3.2 场景(含 simulate.py 等脚本)
│   ├── ml_training/                # 简单 PyTorch 训练 + 指标
│   └── slurm/                      # Slurm 示例 workflow
│
├── tests/
│   ├── unit/                       # models/dag/validator/state/retry/policy
│   ├── integration/                # local executor/sqlite/resume/artifacts
│   ├── examples/                   # 每个 examples/* 跑通断言
│   ├── e2e/                        # demo_1_4.py(§19)
│   └── perf/                       # NFR-03 基准
│
└── scripts/
    ├── check_deps.py               # §5.2 依赖方向检查
    ├── make_demo.sh                # 本地一键演示
    └── ci_slurm_smoke.sh           # 有集群时的冒烟脚本
```

---

## 16. 测试与质量保障

### 16.1 测试金字塔

| 层 | 覆盖内容 | 目标 |
| --- | --- | --- |
| unit | models 校验、dag、validator 规则矩阵、retry 计算、policy、状态机迁移 | ≥ 90% 行覆盖(unit) |
| integration | LocalExecutor 真实子进程、SQLite 事务、checkpoint/resume、artifacts 注册 | 全部通过 |
| examples | 每个 examples/ 目录的 workflow 端到端跑通并断言产物 | 全部通过 |
| e2e | 4 个 Demo 自动化(§19) | 全部通过(≥ 90% 稳定率) |
| perf | 100 任务调度开销、CLI 启动时间 | NFR-03 |

### 16.2 测试设计要点

- executor 抽象使 Slurm 测试可用 FakeSlurmExecutor(记录式)注入
- 重试/恢复测试: 注入失败脚本(`exit 137`、sleep+kill)、中途 SIGKILL engine
- 校验规则: 每个错误码至少 1 个正例 + 1 个反例测试

### 16.3 质量门禁(CI,每次 push + PR)

```text
1. ruff check + ruff format --check
2. mypy --strict sciflow/
3. python scripts/check_deps.py        # 依赖方向
4. pytest tests/unit tests/integration --cov
5. pytest tests/examples
6. pytest tests/e2e                    # 4 个 Demo
7. (手动/定期) perf 基准
```

### 16.4 质量目标

- unit 覆盖率 ≥ 90%;整体 ≥ 80%
- mypy strict 零错误;ruff 零错误
- e2e 套件通过率 ≥ 90%(允许偶发 flaky,但 flaky 测试必须修复或标记)

---

## 17. 里程碑计划

### 17.1 Phase 总览(mark.md §25 的工程化)

| Phase | 周期 | 内容 | 出口条件(Exit Criteria) |
| --- | --- | --- | --- |
| Phase 0 — Design | 1 周 | 架构、DSL、接口、仓库骨架 | §7 DSL 定稿;`sciflow init` 可用;CI 绿 |
| Phase 1 — Workflow Engine | 2–3 周 | DAG/Scheduler/Executor/State/CLI | `sciflow run examples/hello_world` 真实跑通 |
| Phase 2 — Reproducibility | 1–2 周 | Checkpoint/Artifact/Provenance/manifest | `sciflow resume` 可恢复;manifest 完整 |
| Phase 3 — Docker / Slurm | 2–3 周 | 三个 Executor 插件 | 同一 workflow 三端可跑;FakeSlurm 测试绿 |
| **Release v0.1-alpha** | – | 以上合入 | **Demo 1–4 全过**(含本地版) |
| Phase 4 — Agent | 2–3 周 | Intent/Planner/Generator/Validator/审批 | `sciflow plan "..."` 生成可运行 workflow |
| Phase 5 — Scientific Skills | 2–3 周 | python/slurm 深化 + 领域 skill 框架 | skill registry + 检索可用 |
| Phase 6 — Recovery Agent | 3–4 周 | 诊断/修复/重试/审批闭环 | Demo 2 全自动(审批后)通过 |
| Phase 7 — UI(第二阶段) | 之后 | Web Dashboard / 图可视化 / 日志流 | 另行立项 |

### 17.2 12 周逐周计划(含每周验收标准)

| 周 | 目标 | 交付物 | 周验收标准(AC) |
| --- | --- | --- | --- |
| 1 | Workflow DSL + 架构 | schema.py、dag.py 骨架、docs/architecture.md、`sciflow init` | workflow.yaml ↔ Workflow 模型 roundtrip 测试通过;环检测单测通过 |
| 2 | DAG + Task Model | dag.py 完整、validator 结构/资源/I/O 规则 | E-001~E-009、E-100~E-106、E-200~E-203 全错误码测试通过 |
| 3 | Local Executor | executors/local.py、engine 单任务路径 | `sciflow run examples/hello_world` 端到端成功,产物生成 |
| 4 | Scheduler + 并行 | scheduler.py、max-concurrency、rich status | parameter_sweep(10 点)并行运行,status 正确显示,DAG 就绪顺序正确 |
| 5 | State + Checkpoint | state.py、checkpoint.py、`resume` | **Demo 3 通过**:kill 进程后 resume 不丢不重 |
| 6 | Artifact + Provenance | store.py、provenance.py、manifest、`report` | **Demo 4 通过**:两版代码 manifest 可区分;artifact sha256 正确 |
| 7 | Docker Executor | docker.py | 同一 workflow 在固定镜像容器内跑通;digest 入 manifest |
| 8 | Slurm Executor | slurm.py、fake_slurm.py | FakeSlurm 全绿;真实集群冒烟脚本可运行(有集群时) |
| 9 | Agent Intent + Planner | provider.py、intent.py、planner.py | `sciflow plan "run parameter sweep from 1 to 100 with 50 points"` 输出有效 Intent |
| 10 | Workflow 生成 + 校验 | generator.py + agent 侧 validator 闭环 | Agent 生成的 workflow 首次通过 validator ≥ 90%;生成失败自动修复 ≤ 3 轮 |
| 11 | 失败诊断 + 重试 | diagnosis.py、retry 闭环、审批 | **Demo 2 通过**:OOM → 自动升内存 → 审批 → 重试成功 |
| 12 | Demo + 文档 + v0.1 | e2e 套件、README、LICENSE、CI 全绿 | **Demo 1–4 自动化全过**;发布 v0.1;§18 门禁 checklist 全勾 |

### 17.3 排期原则

- 每周 AC 未过 → 该周工作不结束;宁可砍下周内容,不砍 AC
- Phase 3 结束即 `v0.1-alpha` 可发布(工程层完整,Agent 后置)
- 全程保持 North Star Demo(§19)可见:每周演示一次当前进度

---

## 18. 验收标准

### 18.1 四个 Demo(同时是 e2e 自动化测试)

**Demo 1 — 端到端参数扫描**
```text
用户: "Run a parameter sweep from 1 to 100 with 50 points."
系统: Generate workflow → Run 50 jobs → Collect results → Analyze → Plot
断言: 50 任务全部 SUCCEEDED;results.csv/metrics.json/figure.png 存在且已注册;
      manifest.json 完整;report.md 生成
```

**Demo 2 — 失败诊断与修复**
```text
job 17 → OOM
系统: detect → diagnose → increase memory → approval → retry → success
断言: task_events 含 retrying 记录;重试后 SUCCEEDED;audit.log 有审批记录;
      重试后的资源(内存)已按 repair 生效
```

**Demo 3 — 崩溃恢复**
```text
job 1 ✓ job 2 ✓ job 3 ✓ job 4 running → kill engine
sciflow resume → 继续执行
断言: 1–3 状态保持 SUCCEEDED 且未被重跑;4 重跑或继续;最终全部完成
```

**Demo 4 — 代码版本可复现性**
```text
git commit A → run A;git commit B → run B
断言: 两次 run 的 manifest 中 code 哈希不同;输出可区分;
      相同 code+config 重跑 → 关键 artifact sha256 一致(确定性任务)
```

### 18.2 v0.1 发布门禁 Checklist

- [ ] Demo 1–4 自动化测试全部通过(CI)
- [ ] `sciflow plan` + `sciflow run` 全链路手工演示成功(§18.3 North Star Demo)
- [ ] 单元覆盖率 ≥ 90%,mypy strict、ruff 零错误
- [ ] `scripts/check_deps.py` 通过(runtime 无 LLM 依赖)
- [ ] README 完整(定位、安装、5 分钟快速开始、Demo 说明)
- [ ] LICENSE 与贡献指南就绪
- [ ] 无已知 P0 bug

---
### 18.3 v0.1 完整用户交互示例(North Star Demo)

以下展示从 `sciflow plan` 到 `sciflow run`、到失败诊断、到修复重试、到最终产物的完整终端交互。
这是 v0.1 的 North Star Demo——**如果你能把这一条完整链路做出来,这个项目就已经非常像样了。**

```text
$ sciflow plan \
  "Run my simulation with x from 1 to 100,
   use 16 CPUs, analyze the results and
   generate a plot."

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

```text
$ sciflow run workflow.yaml

generate_parameters       ✓
simulation 01             ✓
simulation 02             ✓
...
simulation 37             ✗ OOM
...
```

Agent 检测到失败,提供诊断与修复建议:

```text
Detected failure:
simulation_37
Cause: Out Of Memory

Proposed action:
memory 8GB → 16GB

Approve retry? [Y/n]
```

```text
simulation_37             ✓
collect_results            ✓
analysis                   ✓
visualization              ✓
```

最终产出:

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

> **这条链路就是 v0.1 的终极验收标准。** 12 周的全部工作,就是为了让这一个故事完整跑通。


## 19. 核心指标(度量与采集)

| 维度 | 指标 | 目标(v0.1) | 采集方式 |
| --- | --- | --- | --- |
| Reliability | workflow success rate | ≥ 90%(e2e 套件) | CI 报告 |
| Reliability | recovery success rate | Demo 3 100% 数据不丢 | e2e 断言 |
| Performance | scheduler overhead(100 任务) | < 100ms | tests/perf |
| Performance | workflow startup | < 1s | tests/perf |
| Cost | LLM tokens / plan | 记录并报告(不设硬限) | agent.usage() → plan 元数据 |
| Cost | LLM calls / plan | 记录 | 同上 |
| Cost | compute utilization | 记录(CPU 峰值、时长) | TaskResult.resource_usage |
| Reproducibility | 同 workflow+env+input → 同结果 | Demo 4 断言通过 | e2e |
| DX | time to create workflow(plan) | < 5 min(演示统计) | 手动记录 |
| DX | lines of config(手写 workflow) | parameter_sweep ≤ 40 行 YAML | 代码审查 |

---

## 20. 风险与缓解

| # | 风险 | 影响 | 缓解 |
| --- | --- | --- | --- |
| R1 | LLM 生成的 workflow 质量不稳定 | Phase 4 延期 | 结构化输出 + 强校验器 + ≤3 轮自修复 + 模板化生成;手写 workflow 永远可用(不依赖 Agent) |
| R2 | Slurm 环境千差万别(版本、插件、配额) | Phase 3 验收难 | Executor 能力探测 + FakeSlurm 测试 + 真实集群冒烟脚本(独立于 CI) |
| R3 | 范围蔓延(想做 UI / 领域 skill) | 12 周计划破裂 | §2.2 非目标清单 + 每周 AC 门禁 + North Star Demo 守卫 |
| R4 | 单开发者精力有限 | 延期 | 依赖极简(§14.2);uv 一条命令可复现环境;CI 全自动 |
| R5 | 重试/修复引入不确定性,违背可复现性 | 科学可信度受损 | 重试与修复全部事件化记录(task_events + audit.log);manifest 含 attempt 与 repair 记录 |
| R6 | Docker daemon 不可用 | Docker 路径不可测 | docker 为可选 executor;local 为默认;CI 用 docker executor 的 smoke 测试(daemon 可用时) |
| R7 | checkpoint/resume 状态不一致 | 数据丢失 | 状态迁移单事务;e2e 注入 kill 测试覆盖 |
| R8 | prompt 成本不可控 | 预算问题 | token 用量全记录;temperature=0;结构化输出控制长度;失败自修复设轮数上限 |

---

## 21. 未来扩展与研究

### 21.1 工程演进(架构已预留)

- **Web UI**(Phase 7): FastAPI + React/Next.js;复用 `sciflow status` 的数据层(只加 API 层,不动 runtime)
- **多后端**: S3/MinIO/HuggingFace artifact store(替换 `artifacts/store.py` 的实现即可)
- **分布式引擎**: 将 `runtime/engine.py` 的调度循环替换为 Dask/Ray 适配器
- **领域 Skill 生态**: OpenFOAM / LAMMPS / GROMACS / PyTorch skill 包,遵循 §10.7 规范

### 21.2 研究问题(论文方向)

| 编号 | 研究问题 | v0.1 需要埋的数据 |
| --- | --- | --- |
| A | LLM → Workflow Translation:如何把自然语言科学意图可靠地转换成 executable DAG | plan 全流程日志:原始 NL、Intent、生成 workflow、校验错误、人工修正 diff → 形成数据集 |
| B | Workflow Optimization:串行 A→B→C 能否自动并行化 | workflow DAG + 实际运行耗时 → 优化前后对比 |
| C | Resource-Aware Planning:精度 vs 计算成本的权衡 | plan 的资源估算 vs 实际用量(TaskResult.resource_usage) |
| D | Failure-Aware Agents:失败诊断→修复→验证→恢复闭环 | 失败样本库:TaskResult + Diagnosis + 修复结果 |
| E | Deterministic Runtime + LLM 分工:什么决策交给 LLM、什么交给确定性系统 | 审计日志:每次 LLM 决策点与人工干预点 |

**建议**: v0.1 起就把 plan/run 的 JSONL 日志视为研究数据集资产,提供 `sciflow export-traces` 命令(低成本,高远期价值)。

---

## 22. 附录

### 22.1 术语表

| 术语 | 定义 |
| --- | --- |
| Workflow | 一组有依赖关系的 Task 组成的有向无环图(DAG) |
| Task | 最小执行单元(python/shell/docker/slurm) |
| Run | 一次 workflow 执行实例,有独立 run 目录与状态 |
| Checkpoint | 任务成功后的状态快照,用于断点续跑 |
| Artifact | 任务产物(文件),注册路径、类型、SHA256 |
| Provenance | 产物与输入、代码、环境之间的完整追溯关系 |
| Manifest | 一次 run 的可复现性清单(manifest.json) |
| Skill | Agent 理解科学工具的方式(capabilities + constraints + error_handling) |
| Intent | 自然语言请求的结构化表示(FR-18) |

### 22.2 环境变量汇总

| 变量 | 用途 |
| --- | --- |
| `SCIFFLOW_HOME` | 状态库与缓存目录(默认 `~/.local/share/sciflow`) |
| `SCIFFLOW_LLM_PROVIDER` / `_MODEL` / `_API_KEY` / `_BASE_URL` | LLM 配置(§14.3) |
| `SCIFFLOW_NO_COLOR` | CLI 纯文本输出 |
| `SCIFFLOW_LOG_LEVEL` | 默认 INFO |

### 22.3 与 mark.md 章节对照

| mark.md 章节 | 本文档落地位置 |
| --- | --- |
|| §0–§2 定位/用户/场景 | §1–§3, §1.5 |
| §3 设计原则 | §4 |
| §4 总体架构 | §5 |
| §5 仓库结构 | §15 |
| §6–§7 Workflow/Task | §7–§8 |
| §8 Validation | §7.5 |
| §9–§12 Runtime/Scheduler/Executor/Checkpoint | §10.3–§10.4,§11 |
| §13–§14 Artifact/Provenance | §10.5,§12 |
| §15–§19 Agent/Intent/Skills/检索/恢复 | §10.6–§10.7,§13 |
| §20 Human Approval | §13.4 |
| §21–§22 CLI/UI | §10.8,§21.1 |
| §23–§24 技术栈/不绑定 LLM | §14 |
| §25 MVP 顺序 | §17 |
|| §26 成功标准(4 Demos) | §18.1–§18.2 |
|| §31 v0.1 完整链路 | §18.3(North Star Demo) |
| §27 指标 | §19 |
| §28 研究问题 | §21.2 |
|| §29–§32 长期架构/定位/路线 | §1.4,§17,§22.1 |

---

*文档结束。任何与本规格冲突的实现决定,以"先问用户、再改规格、后写代码"的顺序处理。*
