# Changelog

## v1.3.0 (2026-08-22)

调度与运维 — 任务优先级、Prometheus 指标、模板脚手架。

### 新功能

- **任务优先级** — `Task.priority`（默认 0，向后兼容）；并发槽位竞争时按
  `(-priority, 拓扑序)` 调度；`cpilot dag --format json` 输出该字段
- **`/metrics` Prometheus 端点** — runs/tasks 按状态计数、artifacts 总量，
  文本 exposition 格式，无数据库时输出零值
- **`cpilot init --template`** — 内置 hello_world / parameter_sweep(foreach+priority) /
  ml_pipeline / docker_worker 四模板（内嵌代码，pip 安装可用）
- **`cpilot status --json`** — 运行列表/详情结构化输出（与 /api/run/{id} 同构）

### 修复

- **rich 折行破坏机器可读输出** — 窄终端下 rich 会把长 JSON 行折断导致解析失败；
  新增 `print_text()` 原样输出，status/logs/validate/verify/artifacts/dag(svg/json) 全部改走该通道

## v1.2.0 (2026-08-22)

故障恢复闭环 — 让"可恢复"语义严格、失败任务可控重试。

### 修复

- **resume 不再把带失败的运行标成成功** — 此前 resume 跳过 FAILED 任务后
  运行终态判为 SUCCEEDED（假成功）；现在只要存在 FAILED 任务，
  终态如实为 FAILED

### 新功能

- **`cpilot resume --retry-failed`** — 将 FAILED 任务重新入队后续跑；
  CLI 与 `api.resume(retry_failed=True)` 同步支持；
  `StateStore.reset_failed_tasks()` 删除失败状态行（事件保留供审计）
- **`cpilot validate --json`** — 结构化校验报告（passed + issues[code/level/message/location]），
  便于 CI 集成

### 工程

- CI 新增性能基准步骤（`pytest -m perf`，1000 任务调度 <1s 门禁）

## v1.1.0 (2026-08-22)

表达力与韧性 — 原生参数扫描、优雅中断。

### 新功能

- **`foreach` 任务扇出** — 一个模板任务按 `values` 展开为 N 个实例
  （id 为 `<base>_<i>`），`as` 变量在 command/args/env/inputs/outputs 中替换；
  其他任务对模板 base id 的 `depends_on` 自动重写为依赖全部实例；
  values 可引用 `--set` 参数；上限 500 实例；
  展开顺序：includes 合并 → foreach 展开 → 参数替换 → 校验
- **`cpilot run` 优雅中断** — Ctrl-C 不再裸崩：运行标记 CANCELLED、
  提示 resume 命令、exit 130；已完成任务保持持久化可续跑
- **`cpilot logs --json [--limit N]`** — 结构化事件数组输出
- **Dashboard 运行列表状态过滤** — all/running/succeeded/failed 前端筛选

## v1.0.0 (2026-08-22)

组合与稳定化 — 首个稳定版发布。

### 新功能

- **工作流 include 组合** — `includes:` 递归内联子工作流（相对各自文件定位）；
  循环 include 与合并后任务 id 冲突均明确报错；合并先于参数替换与校验
- **`cpilot dag --run <run_id>`** — 渲染运行持久化的依赖图：ascii 标注任务状态
  （✓/✗/▶）、svg 按状态着色、json 含状态表；旧格式运行给出升级提示
- **`computepilot.__version__`** 导出；pyproject 补齐 classifiers/keywords/readme/license

### 发布工程

- **API 稳定承诺** docs/api-stability.md：CLI 命令与退出码、Python API 签名、
  YAML schema、持久化格式、Web 路由自 1.0 起受语义化版本保护
- **e2e Demo 5** — include 组合 + 参数化 + 双次运行 + verify 可复现判定全链路

## v0.9.0 (2026-08-21)

复现性闭环与编程接口 — 让"可复现"可验证、让引擎可被 Python 直接调用。

### 新功能

- **`cpilot verify <run_a> <run_b>`** — 可复现性一键验证：对比 workflow sha256、
  任务状态/退出码、制品 checksum（按 task+type 对齐，跨运行目录可比）；
  exit 0=REPRODUCIBLE / 1=差异 / 2=错误；`--json` 机器可读
- **Python API 层 `computepilot.api`** — `run / resume / status / list_runs /
  artifacts / report / cancel / verify`，同步函数内部桥接 asyncio，
  `state_dir` 参数支持嵌入隔离；Jupyter 无需子进程驱动引擎
- **`cpilot artifacts RUN_ID --get [-o DIR] [--task T]`** — 导出制品文件，
  复制时重算 sha256 与注册值比对，篡改即告警（exit 1）

### 修复

- **artifacts.id 主键冲突** — 此前 id=checksum[:16]，两次运行产出相同内容即触发
  UNIQUE 约束失败；改为按 (run_id, path, checksum) 派生的行唯一标识

## v0.8.0 (2026-08-21)

参数化与运维 — 工作流模板参数、运行数据生命周期管理。

### 新功能

- **工作流参数化** — YAML 中使用 `${key}`（必填）/ `${key:-default}`（默认值）占位符，
  `cpilot run wf.yaml --set key=value` 注入；替换发生在校验之前；
  缺失必填参数时明确报错列出全部缺失项（exit 2）
  - 替换范围：command / args / environment / inputs / outputs
  - `validate --set` 同步支持
- **`cpilot runs` 命令组**
  - `list [--limit N]` — 最近运行一览
  - `clean [--days N] [--dry-run]` — 清理终态旧运行：五表行 + runs/ 目录，非终态保护
- **Dashboard 实时事件页** `/run/{id}/live` — 轮询游标 API 的追加式事件流
- **`cpilot skill new <name>`** — 技能 YAML 脚手架生成

### 改进

- **SQLite WAL 模式** — StateStore 启用 WAL，改善 CLI 与 Dashboard 并发读写

## v0.7.0 (2026-08-21)

正确性与完整性收尾 — 溯源报告补全、实时进度修复、技能检视。

### 修复（"声明了但未兑现"缺陷）

- **`cpilot report` 制品表** — 此前无论是否注册制品，报告恒写 "*No artifacts registered.*"；
  现在渲染完整制品表（ID/任务/类型/大小/SHA256/路径）
- **`manifest.json` artifacts 字段** — 此前恒为空数组，违背 "Everything Reproducible"（spec P3）；
  `ProvenanceBuilder.build_manifest(artifacts=...)` 现输出
  `{id, task_id, path, type, sha256, size}` 可审计引用
- **`status --live` 进度分母** — config 缺失 total_tasks 时不再硬编码 100，
  改用 task_states 中实际记录的任务数
- **`type: shell` 任务支持完整 shell 语义** — 此前经 exec 直接执行，
  重定向/管道/变量展开静默失效（`echo x > f.txt` 会把 `>` 当字面参数）；
  现在 SHELL 任务经 `bash -c` 执行，与类型语义一致（python/docker 任务不变）

### 新功能

- **`cpilot skill show <name>`** — 以 YAML 输出技能完整定义，便于领域技能编写者参考结构
- **`plan --interactive` 会话保存** — 与 `run --interactive` 对齐：对话结束自动保存并提示恢复命令

### 开发质量

- 覆盖率 87% → **93%**（CI 阈值同步上调至 90）
- 新增 CLI 驱动执行器测试 ×34：SlurmExecutor / DockerExecutor / KubernetesExecutor
  全链路（submit/status/cancel/logs/collect）基于 mock subprocess，无需真实集群/Docker/K8s

## v0.6.0 (2026-08-21)

会话可观测性与 API 化 — 让保存的会话、运行数据可查询、可脚本化。

### 新功能

- **`cpilot sessions`** — 会话管理命令组
  - `list` — 已保存交互会话一览（id/阶段/意图/时间）
  - `show <id>` — 完整对话历史 + 提取的 Intent + 恢复提示
  - `clean [--days N]` — 清理旧会话（默认 30 天）
- **JSON API（Dashboard 同源）**
  - `GET /api/runs` — 运行列表
  - `GET /api/run/{id}` — 详情：元数据 + 任务 + 全部事件 + workflow 结构
  - `GET /api/run/{id}/events?after=N` — 增量事件游标轮询（实时 tail 客户端基础）
- **运行详情页 Events 区块** — 最近 20 条任务事件表

### 改进

- **SVG 渲染器提取为共享模块** `cli/svgdag.py` — CLI 与 Dashboard 复用同一实现
- **`cpilot dag --format svg [-o 文件]`** — 独立 SVG 输出（带 width/height 属性，可直接嵌入文档/浏览器打开）

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