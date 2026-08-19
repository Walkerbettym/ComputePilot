# 贡献指南

欢迎贡献 ComputePilot！请遵循以下规范。

## 开发环境

```bash
git clone https://github.com/Walkerbettym/ComputePilot.git
cd ComputePilot
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 代码规范

1. **类型安全**：使用 `mypy --strict computepilot/` 检查，零容忍错误
2. **代码风格**：使用 `ruff check computepilot/ tests/ scripts/`，零容忍错误
3. **依赖方向**：`computepilot/runtime/` 禁止 import `computepilot/agent/` 或 LLM SDK。用 `python scripts/check_deps.py` 验证
4. **模型**：所有数据模型使用 Pydantic v2，禁止使用原始 `dataclass` 定义业务模型
5. **测试覆盖率**：unit ≥ 90%，overall ≥ 80%（渐进目标）

## 测试

```bash
# 单元+集成
pytest tests/unit/ tests/integration/ --cov=computepilot

# 端到端（4 个 Demo）
pytest tests/e2e/ -v

# 全部
pytest tests/ --cov=computepilot
```

## PR 要求

- 通过全部 CI 检查（ruff → mypy → check_deps → pytest）
- 新增代码有对应测试
- 新增功能对应 spec.md（参照 §17 里程碑）
- 不引入 runtime→agent 依赖

## 分支策略

- `main` — 发布分支，始终保持 CI 绿色
- 功能分支从 main 切出，合入前需 squash

## 项目结构

```
computepilot/
├── agent/       # LLM 智能层
├── artifacts/   # 制品与溯源
├── cli/         # 命令行入口
├── executors/   # Local/Docker/Slurm 执行器
├── models/      # Pydantic 数据模型
├── policy/      # 策略引擎
├── runtime/     # 运行时引擎
├── skills/      # 技能注册表
└── workflow/    # DAG/验证/Schema
tests/
├── unit/        # 单元测试
├── integration/ # 集成测试
└── e2e/         # 端到端 Demo 测试
```