# Changelog

## v0.4.0 (2026-08-21)

从"能跑真实用例"到"生产可用" — 稳定性、CLI 全链路集成、监控生态。

### 新功能

- **`cpilot run --interactive`** — 一次完成：自然语言 → Conductor 对话 → 批准 → 执行
- **`cpilot run --from-session <id>`** — 会话持久化（JSON），从上次对话继续规划执行；交互结束自动保存并提示恢复命令
- **Conductor 会话持久化 API** — `save_session` / `load_session` / `list_sessions`
- **`cpilot status --live`** — ExecutionSentinel 实时进度条 + OOM/stalled 异常告警
- **WorkspaceManager** — 多工作区创建/列表/切换/删除
- **Web Dashboard** — FastAPI UI：运行统计卡片、成功率、任务进度条、自动刷新

### 修复

- `cpilot plan` 非交互路径 UnboundLocalError（局部 import 作用域问题）— 该路径此前完全不可用
- webui.py mypy strict 注解缺失

### 开发质量

- 覆盖率 67% → **87%**（目标 ≥80% 达成）
- 新增 74 个 CLI 单元测试（绕开 typer CliRunner 兼容性，直接调用命令函数）
- mypy --strict 66 文件零错误；ruff 零错误
- Docker CI job — docker executor 集成测试在 ubuntu-latest 运行

## v0.3.0 (2026-08-20)

从"能跑"到"真正能用" — K8s 执行器、CLI 交互模式、真实科学用例。

- **Kubernetes 执行器** — `executors/kubernetes.py` + FakeK8s（CI 用），namespace/pod/PV
- **`plan --interactive`** — Conductor 多轮对话澄清模式
- **1000 Genomes demo** — 论文对齐的群体遗传学 e2e 工作流
- CLI 命令测试（14 个）+ Conductor/Sentinel 集成测试

## v0.2.0 (2026-08-19)

论文"管道编排层"对齐 — 从科研问题到可执行 DAG 的智能翻译。

- **技能知识层 v2** — vocabulary_mappings（26 群体/24 染色体/5 分析类型）、parameter_constraints、optimization_strategies
- **VocabularyResolver** — 自然语言 token → 领域规范码
- **Conductor** — 多轮对话编排：路由 → 澄清 → 规划 → 审批门控
- **EnvironmentProbe + 延迟 DAG 生成** — 先探测环境再定最终 DAG
- **ExecutionSentinel** — 进度监控 + stalled/OOM 异常检测
- **population_genetics skill** — 1000 Genomes 领域知识编码

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