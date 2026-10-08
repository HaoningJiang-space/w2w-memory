# 当前任务：真实 routing 驱动的完整 MoE 层

实验只在 `hn072@143.89.78.72` 运行，独立目录
`/Projects/haoning/w2w-full-system-20261009`；eex005 只用于迁移与清理。

唯一主线：复用 `SystemExecution` 和 pinned native BookSim，执行同一 Qwen3
`c0_b1`、layer 0、decode step 17 的 dispatch、分块权重读取、up/gate/down 与 combine。
固定原有 marginal LPT owner、50% home/50% 邻接 peer 驻留与计算/SRAM预算。

比较 B1-real、仅理想化 MC-ready 之后的 NoC 返回、加宽一档 compute NoC。
后两者分别是返回通路诊断和有显式线资源开销的强基线。先完成 ideal 原生供给，
再对同图使用既有 Ramulator HBM2；两种 DRAM profile 的结果分别报告。

当前入口：`python -m w2w.experiments.run_moe_layer`；网络适配器在
`w2w/network/booksim_backend.py`，任务图在 `w2w/workloads/moe_task_graph.py`。
2×2 native 任务链已在 hn072 完成；不再开展 BookSim 验收矩阵。
保留日常回归，只为出现的具体问题补回归。

交付本层完成时间、实际请求/响应/激活流量、拥塞资源和任务时间线，随后据结果
决定研究 memory attachment、compute NoC 还是数据组织。暂不增加 Direct HB、
endpoint RTL、FIFO 或 placement 搜索；不把 FFN 层时序写成完整 LLM 或数值推理结果。

旧“下一步”均移入 [历史索引](NEXT_TASK_HISTORY.md)。
