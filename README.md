# ComputePilot

> 面向科学计算的开源 Agentic Workflow Runtime —— 让科研人员通过自然语言生成可验证、可执行、可恢复、可复现的计算工作流。

**Agent + Workflow + Reproducibility**

用户用自然语言描述计算实验,ComputePilot 生成可执行的工作流 DAG,在本地、Docker 或 Slurm 集群上可靠运行,自动处理失败诊断与恢复,最终产出可复现的实验报告。

三个核心能力:

```
理解 → 规划 → 执行(可靠运行时) → 复现(产物 + 溯源)
```

## 文档

- [`spec.md`](spec.md) — 项目落地规格说明书(22 章 + 附录,详细设计规格)
- [`mark.md`](mark.md) — 原始项目设计方案(32 节)
- [`2604.21910.pdf`](2604.21910.pdf) — 相关论文

## 核心理念

> **先做一个真正能用的软件 → 再加入 Agent → 再加入 Scientific Computing → 最后自然长出研究问题。**

不是为论文做 benchmark,而是先做一个真的有用的工程系统,然后从工程问题里长出研究问题。

## 许可

MIT