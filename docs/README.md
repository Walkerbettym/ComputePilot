# ComputePilot 文档

## 📖 核心文档

| 文档 | 说明 |
|---|---|
| [`README.md`](../README.md) | 项目首页、安装、5 分钟快速开始 |
| [`spec.md`](spec.md) | **落地规格说明书**（22 章，v0.1–v0.3 实现依据） |
| [`mark.md`](mark.md) | **原始设计方案**（32 节，项目起源） |
| [`architecture.md`](architecture.md) | **系统架构**（四层、模块、依赖方向） |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本发布记录 |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | 贡献指南 |

## 📋 实施计划

| 计划 | 说明 |
|---|---|
| [`plans/v0.2-plan.md`](plans/v0.2-plan.md) | v0.2 计划（Conductor/Skills/探测/哨兵） |
| [`plans/v0.3-plan.md`](plans/v0.3-plan.md) | v0.3 计划（K8s/CLI 交互/覆盖率） |

## 📁 引用论文

- [`2604.21910.pdf`](../2604.21910.pdf) — "From Research Question to Scientific Workflow" (AGH 大学)
  - 论文的三层架构（语义层/确定性层/知识层）是 ComputePilot 的架构理论基础
  - v0.1：确定性运行时 → v0.2：论文三层架构 → v0.3：云执行器

## 🗂 模块结构

```
computepilot/
├── agent/         # 智能层（LLM 意图提取、规划、诊断、词汇解析）
├── artifacts/     # 制品存储与溯源
├── cli/           # 命令行入口（11 命令）
├── executors/     # 执行器（local/docker/slurm/kubernetes + fake 实现）
├── models/        # Pydantic 数据模型
├── policy/        # �略引擎
├── runtime/       # �行时引擎（engine/scheduler/state/checkpoint/retry/sentinel/probe）
├── skills/        # 䏝能注册表（python/shell/docker/slurm/ population_genetics）
└── workflow/      # DAG/䱇证/Schema
```