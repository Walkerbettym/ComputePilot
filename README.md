# ComputePilot

> **v1.0** — 自本版本起遵循语义化版本，公开面见 [docs/api-stability.md](docs/api-stability.md)

> **面向科学计算的开源 Agentic Workflow Runtime — 让科研人员通过自然语言生成可验证、可执行、可恢复、可复现的计算工作流。**

**Agent + Workflow + Reproducibility**

用户用自然语言描述计算实验，ComputePilot 生成可执行的工作流 DAG，在本地、Docker 或 Slurm 集群上可靠运行，自动处理失败诊断与恢复，最终产出可复现的实验报告。

```
理解 → 规划 → 执行(可靠运行时) → 复现(产物 + 溯源)
```

---

## 核心设计原则

| 原则 | 说明 |
|---|---|
| **Agent ≠ Runtime** | Agent 负责理解/规划/诊断；Runtime 负责执行/调度/状态/重试。Runtime 零 LLM 依赖 |
| **Workflow First** | Agent 输出结构化 Workflow，而非 shell 命令 |
| **Everything Reproducible** | 每次运行保存 code/config/workflow/params/logs/结果/sha256 |
| **Human-in-the-loop** | 高成本操作允许人工批准 |
| **Local First** | 先支持 Local → Docker → Slurm，后接云 |

---

## 安装

需要 **Python ≥ 3.11**。

```bash
# 1. 克隆仓库
git clone https://github.com/Walkerbettym/ComputePilot.git
cd ComputePilot

# 2. 创建虚拟环境并安装
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. 验证
cpilot --help
```

---

## 5 分钟快速开始

### 0. 初始化一个工作流项目

```bash
cpilot init my_experiment
cd my_experiment
```

这会生成 `workflow.yaml`：

```yaml
name: my_workflow
description: "My ComputePilot workflow"
tasks:
  - id: hello
    command: echo "Hello, ComputePilot!"
    type: shell
```

参数扫描用 `foreach` 一行扇出（v1.1+）：

```yaml
tasks:
  - id: simulate
    foreach: { values: [10, 20, 30], as: n }
    command: python sim.py --n ${n}
```

### 1. 校验

```bash
cpilot validate workflow.yaml
# ✓ 校验通过
```

### 2. 运行

```bash
cpilot run workflow.yaml
# 确认执行？[Y/n]
```

### 3. 查看状态与日志

```bash
cpilot status            # 查看所有运行
cpilot status <run-id>   # 查看某个运行详情
cpilot logs <run-id>     # 查看任务事件日志
```

### 4. 从自然语言生成工作流（Agent）

```bash
# 需要设置 OpenAI 兼容 API（或设置 SCIFLOW_LLM_PROVIDER）
export SCIFLOW_LLM_API_KEY="sk-..."
export SCIFLOW_LLM_MODEL="gpt-4o-mini"

cpilot plan "Run a parameter sweep from 1 to 100 with 10 points, use 8 CPUs"
# → 生成 workflow.yaml + 成本估算
```

### 5. 崩溃恢复

如果运行中途被杀，可以恢复：

```bash
cpilot resume <run-id>
# 从最后一个成功任务继续，不丢已完成、不重复执行
```

### 6. 产物与溯源报告

```bash
cpilot artifacts <run-id>   # 列出制品（路径/sha256/大小）
cpilot report <run-id>      # 生成 report.md + manifest.json（可复现）
```

---

## 四个 Demo（也是 e2e 测试）

| Demo | 场景 | 验证 |
|---|---|---|
| **Demo 1** | 端到端参数扫描（generate→simulate→analyze→visualize） | 50 任务全过 + 产物生成 |
| **Demo 2** | 失败诊断修复（OOM→升内存→重试→成功） | task_events 含 retrying + 内存修复生效 |
| **Demo 3** | 崩溃恢复（kill→resume→不丢不重） | 已完成任务不重跑，最终全部完成 |
| **Demo 4** | 可复现性（相同输入→相同 sha256；不同→不同） | artifact checksum 可区分 |

一键运行全部：`./scripts/make_demo.sh --coverage`

---

## 文档

- [`spec.md`](spec.md) — 落地规格说明书（22 章，v0.1 唯一实现依据）
- [`mark.md`](mark.md) — 原始项目设计方案（32 节）
- [`docs/architecture.md`](docs/architecture.md) — 系统架构
- [`2604.21910.pdf`](2604.21910.pdf) — 相关论文

---

## 命令速查

| 命令 | 作用 |
|---|---|
| `cpilot init` | 初始化工作流项目 |
| `cpilot validate` | 校验 workflow.yaml（24 条规则） |
| `cpilot dag` | 可视化任务依赖图（ascii/mermaid/json） |
| `cpilot run` | 执行工作流（Local/Docker/Slurm/K8s；`--set k=v` 参数化） |
| `cpilot plan` | 从自然语言生成工作流 |
| `cpilot status` | 查看运行状态 |
| `cpilot logs` | 查看任务事件日志（`--follow` 实时跟踪） |
| `cpilot resume` | 从检查点恢复 |
| `cpilot cancel` | 取消运行 |
| `cpilot artifacts` | 列出/导出制品（`--get` 校验 sha256） |
| `cpilot verify` | 对比两次运行的可复现性 |
| `cpilot report` | 生成溯源报告 |
| `cpilot skill` | 管理技能注册表 |
| `cpilot sessions` | 查看/清理已保存的交互会话 |
| `cpilot runs` | 运行历史管理（list/clean） |

---

## 开发

```bash
# 类型检查（strict）
mypy --strict computepilot/

# 代码风格
ruff check computepilot/ tests/ scripts/

# 依赖方向检查（runtime 不允许 imports agent）
python scripts/check_deps.py

# 运行全部测试（unit + integration + e2e）
pytest tests/unit/ tests/integration/ tests/e2e/ --cov=computepilot
```

CI 每次 push 自动运行上述全部检查（含 coverage ≥ 90%，当前 93%）。

---

## Python API

```python
from computepilot import api

run = api.run("workflow.yaml", params={"epochs": 50})  # 阻塞至完成
print(run.id, run.status)
api.verify("run_a", "run_b")  # {"reproducible": true/false, ...}
```

支持 `run / resume / status / list_runs / artifacts / report / cancel / verify`。

---

## 技术栈

Python ≥3.11 · Pydantic v2 · Typer · asyncio · SQLite · Rich · PyYAML · httpx · pytest · ruff · mypy

## 许可

MIT
