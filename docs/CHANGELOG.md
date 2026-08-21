# Changelog

## v0.5.0 (2026-08-21)

从"生产可用"到"规模与领域生态"。

### 新功能

- **`cpilot dag`** — 任务依赖图可视化：ascii 树（终端）/ mermaid（Markdown 可嵌入）/ json（机器可读）；环检测报错
- **HPC 领域 Skill ×3（NG-5 兑现）**
  - `openfoam` — 求解器/湍流模型/网格词汇表，发散自动降时间步，Reynolds 参数约束
  - `gromacs` — 力场/系综/溶剂词汇表，温度/步长约束，GPU 资源默认
  - `lammps` — 势函数/系综/材料词汇表，原子数/应变率约束，LOST_ATOMS 自愈动作
  - Conductor 自动路由领域查询（如 "sst turbulence" → openfoam）
- **`cpilot logs --follow`** — tail -f 式实时事件跟踪，支持 `--task` 过滤组合
- **Dashboard DAG 视图** — 运行详情页内嵌分层 SVG 依赖图（零外部依赖），节点按任务状态着色；引擎持久化 workflow 结构到 config_json

### 工具

- **`scripts/slurm_smoke.sh`** — 真实集群冒烟测试（sbatch/sacct/scancel 全链路，独立于 CI）

### 修复

- **CLI 入口在 Python 3.14 完全不可用** — typer 0.27 不再支持 `app.command()(sub_typer)` 嵌套写法，改用 `add_typer`；此前 `cpilot --help` 即崩溃

### 性能

- 新增 1000-task 调度基准：宽图 < 1s、链式 ready_tasks ×1000 < 2s（全部通过）

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