# 当前任务：闭合 wafer machine 与有限流式返回

Home / Pair / 4-way 的九项固定驻留执行已完成；[结果](../reports/B1_RESIDENCY_STUDY_REPORT.md)
限定于当前合成 6×6 stitched
mesh＋36-channel HBM2 reference。之后不扩大驻留 DSE，不先开发 Direct HB 或 RTL。
[物理机器与服务边界设计](../methods/WAFER_MACHINE_CLOSURE.md)是唯一后续实施合同。

按三个可归因的更新推进：

1. **机器定义生成 SystemSpec**：reticle 与端口的物理坐标共同生成合法 C–C/HB 路径，
   同一线段给出长度、流水、credit 和成本。参数注明来源/假设；新机器另给身份，
   不把现有每边 10 mm、2-cycle 配置追认成真实 wafer。对齐矩形不默认具有邻居 HB。
2. **细粒度就绪接入现有 BookSim**：保留 4 KiB descriptor、请求数量、MC/outstanding、
   包格式与地址；native ticket 记录 offset，有限 bitmap 驱动连续可供 flit，
   本地 DMA 同样流式。明确 payload 所有权和 slot 释放，不靠拆小请求增加并发。
   与旧整 descriptor 返回同任务比较；不离线从旧时间中减一个常数。
3. **原生 profile**：HBM2 保持 controller-ready 边界；新独立 RWDL 配置依据容量、
   通道数、接口宽度与频率构造，并落实命令/刷新/返回资源。不能将 HBM2 的 bandwidth
   直接乘倍数，或在回调后免费生成 pre-HB 分叉。缺失时序明确为假设。

复用统一 kernel、native BookSim、Ramulator 和已有 routing；不重新开发 simulator、
不启动 BookSim 验收 campaign。日常回归照常，仅核验本次增加的因果与有限容量合同。
单层结果不能写成完整 LLM、物理校准或制造可行性已证明。

实验只在 hn072 的隔离 `/Projects/haoning/w2w-full-system-*` 目录，源码经 Git；
不改另一位开发者的 RTL 和 wafer_simulator。旧任务见[历史索引](NEXT_TASK_HISTORY.md)。
