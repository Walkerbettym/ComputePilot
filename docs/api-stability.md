# API 稳定承诺（自 v1.0 起）

ComputePilot 遵循 [语义化版本](https://semver.org/lang/zh-CN/)：
**MAJOR** 破坏性变更 / **MINOR** 向后兼容新功能 / **PATCH** 缺陷修复。

## 公开面清单

以下接口自 1.0 起受语义化版本保护：

### 1. CLI 命令

`cpilot init · validate · dag · run · status · logs · plan · artifacts · report ·
resume · cancel · verify · skill · sessions · runs`

各命令的参数名与退出码约定：
- `0` 成功；`1` 运行失败/差异/未找到；`2` 用法错误/文件缺失/校验未通过

### 2. Python API（`computepilot.api`）

```python
run(workflow_path, *, params=None, executor="local", max_concurrency=4,
    state_dir=None, run_dir=None) -> Run
resume(run_id, workflow_path, *, max_concurrency=4, state_dir=None) -> Run
status(run_id, *, state_dir=None) -> dict          # KeyError 若不存在
list_runs(limit=20, *, state_dir=None) -> list[dict]
artifacts(run_id, *, state_dir=None) -> list[dict]
report(run_id, *, out_dir=None, state_dir=None) -> Path
cancel(run_id, *, state_dir=None) -> None
verify(run_a, run_b, *, state_dir=None) -> dict    # {"reproducible": bool, "checks": [...]}
```

### 3. Workflow YAML Schema

顶层字段 `name / description / includes / defaults / tasks`；
任务字段见 `computepilot.models.workflow.Task`；参数占位符 `${key}`、`${key:-default}`。

### 4. 持久化格式

- SQLite 五表结构（runs/task_states/task_events/artifacts/approvals）
- `config_json` 中的 `workflow.tasks` 结构（v0.5+）与 `total_tasks`
- 会话 JSON（sessions 目录）、manifest.json schema_version=1

### 5. Web 接口

页面路由 `/`、`/run/{id}`、`/run/{id}/live`；
API `/api/runs`、`/api/run/{id}`、`/api/run/{id}/events?after=N`。

---

## 非公开面（可能随版本变化）

- `computepilot.cli.*` 内部函数（命令实现细节）
- `computepilot.runtime.*` / `computepilot.executors.*` 的类签名
  （Protocol 层面稳定，具体方法可能扩展）
- SQLite 表内新增列（始终向后兼容追加）

## 弃用流程

破坏性变更：MINOR 版本先以 `DeprecationWarning` 过渡一个周期，MAJOR 版本移除。
