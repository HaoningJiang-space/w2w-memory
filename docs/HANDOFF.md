# W2W Memory-on-Logic 开发交接

2026-10-09：Home / Pair / 4-way 的九项完整 routed FFN 层执行与事件核验已完成。
**当前结果：[驻留系统报告](reports/B1_RESIDENCY_STUDY_REPORT.md)。**

| 输入 | Home-only | Pair | 4-way |
|---|---:|---:|---:|
| c0_b1 原单 token | 661.173 μs | 681.736 μs | 347.679 μs |
| c1_b1 独立单 token | 661.163 μs | 681.726 μs | 524.448 μs |
| c2_b4 预定四 token | 1,981.770 μs | 1,706.464 μs | 1,041.569 μs |

全部保持同一机器、冻结 expert owner 与逻辑任务。Pair 两单请求比 Home 慢 3.11%，
四 token 则快 13.89%；4-way 相对 Pair 快 49.00%、23.07%、38.96%，约增加一倍
NoC wire 流量。这里“快”指本层完成时间缩短，不是完整 LLM 加速。

现有系统属于 HBM2 reference＋合成 stitched mesh，整 descriptor ready 后返回。
**物理 wafer 建模尚未闭合。** 下一步是[机器定义与流式返回](methods/WAFER_MACHINE_CLOSURE.md)，
具体顺序见[唯一当前任务](handoff/NEXT_TASK.md)。保留 kernel、BookSim、Ramulator，
不扩驻留 DSE、不开发 Direct HB/RTL 变体，不把 HBM2 重命名成定制 WoW DRAM。

## 代码与证据入口

| 内容 | 入口 |
|---|---|
| 统一任务/事务时间线 | `w2w/system/kernel.py` |
| native 网络 / 原生内存 | `network/booksim_backend.py` / `memory/backend.py` |
| 三种全专家驻留与 FFN 编译 | `workloads/moe_task_graph.py` |
| 注册与运行 / 完成记录分析 | `run_residency_study` / `analyze_residency_study` |
| 固定样本与对照协议 | [B1_RESIDENCY_STUDY](methods/B1_RESIDENCY_STUDY.md) |
| 九项摘要、输入、哈希 | `artifacts/results/system/b1_residency/` |
| 运行日志与导出清单 | `artifacts/provenance/b1_residency/` |
| 完整事件与冻结源码 | hn072 `w2w-full-system-residency-20261009` |

Pair/4-way 执行源码 `fb23c3c`；用户随后要求的 Home 独立登记，源码 `c9599bd`；
分析 `b0aeb4b`。37 项相关回归在原六项运行前通过；各 case 都做原有事件/资源审计。
前轮[三种网络条件结果](reports/MOE_LAYER_SYSTEM_REPORT.md)与历史 RTL/read-only
证据保留原身份；旧交接在 [历史](HANDOFF_HISTORY.md)，不按旧“下一步”重复实验。

## 服务器与协作

- 新构建、测试、实验只在 `hn072@143.89.78.72`，本轮目录
  `/Projects/haoning/w2w-full-system-residency-20261009`，复用 `/Projects/haoning/w2w/.venv`。
- 本地 `/home/abc/jhn/w2w-memory` 开发源代码，`origin` 指向
  [HaoningJiang-space/w2w-memory](https://github.com/HaoningJiang-space/w2w-memory)，维护 `main`。
  hn072 主仓库使用 `research-origin`；拉取前检查工作区，不修改运行中的源码树。
- eex005 退出新实验；九个停用 W2W 工作树经归档、校验与恢复后删除，观测释放
  1.68 GB。[迁移与清理记录](operations/SERVER_STORAGE.md)。
- 另一位开发者的 RTL 和 `/Projects/haoning/wafer_simulator` 工作区保留，不覆盖。
  凭据、原始采集、native builds 与环境不进 Git。
