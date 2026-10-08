# 当前任务：用完整层反馈定位 MC/DRAM 与静态驻留

前一项已完成：native BookSim 接入，真实 routing 的 dispatch、权重读取、计算、
combine 跑完；三种网络条件各在 IdealBanks 与原生 Ramulator HBM2 执行。
[结果报告](../reports/MOE_LAYER_SYSTEM_REPORT.md)是当前判断依据。

HBM2 的 B1 为 681.736 μs，理想返回为 712.581 μs，加宽 NoC 为 691.823 μs。
12/36 个 memory 有请求，其中四个承担其他活跃 memory 的两倍字节。
请求时序变化伴随 DRAM 行冲突变化；这不是免费直连的全局上界，也不是 Direct HB
必然无效的结论。IdealBanks 下网络改动能加速，说明结论取决于原生供给模型。

下一步保持同一 kernel、NoC、HBM2、计算与 SRAM，从既有事件记录分开检查：
MC descriptor 扩展/排队、bank/row 局部性、每个原生 channel 的字节负载。
据此只改变一个因素做同任务对照：例如在冻结 owner 与容量约束下改变静态驻留，
或在地址集合完全不变时改善 controller admission 顺序。先写出所改变的资源与
预期关键路径，再运行；不要同时释放 owner、伙伴、比例、接口和调度。

后续推广使用预先选定的独立 cohort，不按结果挑 routing。当前单 token 结果不能
代表 batch serving；扩展输入时继续显式分块及权重复用，不扩大 SRAM 绕过问题。
B0-local 和可制造 B2 Direct HB 尚未成为本轮完成结果。

所有构建、测试、实验在 `hn072@143.89.78.72` 的隔离目录；eex005 只供迁移/清理。
沿用现有组件与日常回归，不新增 BookSim 验收 campaign，不开展 endpoint RTL 变体。
旧任务在 [历史索引](NEXT_TASK_HISTORY.md)。
