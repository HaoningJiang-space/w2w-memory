# W2W Memory-on-Logic 开发交接

2026-10-09：native BookSim 已接入现有 `SystemExecution`；真实 routing 驱动的一个
routed MoE FFN 层已执行 dispatch、分块权重读取、计算与 combine。
**当前结果与下一步判断：[完整层报告](reports/MOE_LAYER_SYSTEM_REPORT.md)。**

| 运行 | IdealBanks 层完成时间 | Ramulator HBM2 层完成时间 |
|---|---:|---:|
| B1-real | 170.899 μs | 681.736 μs |
| B1-return-ideal | 131.631 μs | 712.581 μs |
| B1-wide-NoC | 139.675 μs | 691.823 μs |

六项使用相同任务图、expert owner 与地址驻留。两种 DRAM profile 的原生预算不同，
只能在各自列内比较。本轮覆盖一个 token、八个专家、一个 routed FFN 层；不是完整
LLM 延迟，也没有验证数值输出。34 项既有 system/DRAM 回归通过，无 native skip。

HBM2 下，最忙 compute 链路平均利用率 6.09%，改变返回网络未改善完成时间；
关键 expert 的等待主要在最后 native-ready 之前。下一步只研究既有 NoC 上的
MC/DRAM 服务与静态驻留，具体对照见 [唯一当前任务](handoff/NEXT_TASK.md)。
暂不增加 Direct HB、endpoint RTL 或新的跨 bank engine pool。

## 代码与证据入口

| 内容 | 入口 |
|---|---|
| 统一任务/事务时间线 | `w2w/system/kernel.py` |
| 复用 native 网络 | `w2w/network/booksim_backend.py`；wafer_simulator pin `0c56c24` |
| 完整层任务编译 | `w2w/workloads/moe_task_graph.py` |
| Ideal / pinned Ramulator | `w2w/memory/backend.py`、`w2w/service/dram/` |
| 运行与静态分析 | `run_moe_layer`、`analyze_moe_layer` |
| 输入/机器/接口合同 | [MOE_LAYER_SYSTEM](methods/MOE_LAYER_SYSTEM.md) |
| 六项摘要与哈希 | `artifacts/results/system/moe_layer/` |
| 原始完整事务记录 | hn072 的 `w2w-full-system-20261009/layer-*-3a498c1/` |

执行源码固定 `3a498c1b9347e298e7c5766885069d8d57ddf9ba`。分析与报告提交不重写
旧实验身份。Python CreditNetwork 留作小型参考；历史 LP/read replay、匹配与 RTL
保留原 scope，导航见 [历史交接](HANDOFF_HISTORY.md)、[研究状态](RESEARCH_STATUS.md)。

## 服务器与协作

- 新构建、测试、实验只在 `hn072@143.89.78.72`，本轮目录
  `/Projects/haoning/w2w-full-system-20261009`，复用 `/Projects/haoning/w2w/.venv`。
- 本地 `/home/abc/jhn/w2w-memory` 开发源代码，`origin` 指向
  [HaoningJiang-space/w2w-memory](https://github.com/HaoningJiang-space/w2w-memory)，维护 `main`。
  hn072 主仓库使用 `research-origin`；拉取前检查工作区，不修改运行中的源码树。
- eex005 退出新实验；九个停用 W2W 工作树经归档、校验与恢复后删除，观测释放
  1.68 GB。[迁移与清理记录](operations/SERVER_STORAGE.md)。
- 另一位开发者的 RTL 和 `/Projects/haoning/wafer_simulator` 工作区保留，不覆盖。
  凭据、原始采集、native builds 与环境不进 Git。
