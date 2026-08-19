# Changelog

## v0.1.0 (2026-08-19)

ComputePilot 首个正式发布版本。

### 核心架构

三层次架构（对齐论文设计理念）：
- **语义层** — IntentExtractor 将自然语言提取为结构化意图（需 LLM key）
- **确定性层** — Planner 将 Intent 转换为 Workflow DAG；Runtime 调度执行（零 LLM 依赖）
- **知识层** — Skill 注册和检索系统

### CLI 命令（11 个）

`cpilot init` · `validate` · `run` · `plan` · `status` · `logs` · `resume` · `cancel` · `artifacts` · `report` · `skill`

### 引擎特性

- DAG 调度：拓扑排序 + 环检测 + 并发控制
- 4 执行器：Local（子进程）、Docker（容器）、Slurm（HPC）、FakeSlurm（CI）
- 状态持久化：SQLite 5 表（runs/task_states/task_events/artifacts/approvals）
- 检查点 + 崩溃恢复（`cpilot resume`，不丢不重）
- 重试策略：none/fixed/exponential 3 种 backoff
- 失败诊断：6 分类（OOM/超时/缺文件/语法/节点/未知）+ 自动修复
- 看门狗超时：任务超时自动 kill（默认 1h）
- 策略引擎：CPU/GPU/成本上限检查 + 审批门控
- 制品溯源：ArtifactStore（sha256）+ ProvenanceBuilder（manifest + git SHA）
- 任务级缓存：相同命令+输入→SKIPPED（FR-23）
- JSON 结构化日志（FR-24）

### Agent 组件

- IntentExtractor（语义提取，需 LLM）
- Planner（确定性规划）
- SkillRetriever（关键词检索）
- CostEstimator（成本估算）
- Diagnoser（规则分类器）
- Auto-Repair 流水线（OOM→升内存→重试→成功）

### 开发质量

- Python 3.11/3.12/3.13 CI 全绿
- mypy strict 零错误（57 文件）
- ruff 零错误 + format 一致性
- 253 测试（238 单元/集成 + 8 e2e + 7 示例）
- 覆盖率 ≥ 65%
- runtime 零 LLM 依赖（check_deps.py 强制执行）

### 示例工作流

- `hello_world` — 入门
- `parameter_sweep` — 参数扫描（3 任务链）
- `ml_pipeline` — 逻辑回归训练评估（3 任务）
- `docker_worker` — Docker 质数计算（2 任务）
- `data_processing` — Shell + Python 混合清洗（3 任务）