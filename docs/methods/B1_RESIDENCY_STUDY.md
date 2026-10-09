# B1 固定 Pair 与邻近 4-way 驻留：预先登记

2026-10-09，在任何本轮性能执行前固定本协议。

只改变静态权重驻留。沿用 `49dcce7` 的真实返回 native BookSim、Ramulator HBM2、
compute owner、计算分块、2 MiB SRAM、MC32/outstanding32、4 KiB descriptor、
256 B/ns NoC 和原有 native callback 边界。冻结 Direct HB/configurable 开发。

## 布局规则

Pair 保持既有实现、对象顺序和地址：每专家每个 intermediate tile 的一半在
owner，一半在 `owner XOR 1`，按 64 KiB 段交错发起。

4-way 将 6×6 网格划成九个固定、不重叠的 2×2 区域。每专家的四个来源依次为
home、水平 peer、同区域的垂直邻居、对角邻居；每个来源存四分之一。
区域只由 owner 坐标决定，对全部 128 个专家相同，不读取活跃 expert 集合。
同一个 policy 在所有请求/cohort 下使用字节一致的完整对象布局。

沿用 64 KiB 段交错发起；每 128-wide compute block 在 Pair 每 shard 的尾部
为 192 B，4-way 为 96 B。尾部均为 native 32 B 的整数倍，额外 descriptor、
header/padding 和远端 hop 如实收费；不以额外窗口抵消 4-way 的通信成本。

对象驻留允许改变物理 memory/bank/row 地址。逻辑任务、每个 task 的权重总字节、
计算、DataEdge、owner 与源 token 不变。不能要求物理地址集合也相同。

## 运行顺序与预定样本

先执行 HBM2＋真实网络下的 `c0_b1` Pair/4-way。`c0_b1` 保持上轮第一个请求、
layer 0、decode step 17（1-based），Pair 编译图和机器须与已归档结果逐字段相同。
若得到可解释的架构信号，再执行下列已登记样本，不依据快慢挑选：

| 输入 | 既有 split 中的选取规则 | 用途 |
|---|---|---|
| c0_b1 | group 0 的第一个 request | 主要诊断，复用上轮逻辑任务 |
| c1_b1 | group 1 的第一个 request | 独立请求 |
| c2_b4 | group 2 的前四个 requests | 不重叠的多 token batch |

都使用 layer 0、decode step 17；token 依次归属 c0…c(batch−1)。输入已在过去
读阶段实验中归档，不称新采集的未见 corpus；它们与本轮主请求及训练 owner 的
拟合输入分离。各 cohort 的 token 共享同专家 weight tile，不按 token 重复冷读。
先登记所有六项的输入 ID/哈希与全体专家布局，再执行任一结果。

## 输出与判断

主指标为 routed FFN 层完成时间；辅以每 memory 字节、MC 接纳等待、descriptor
native-ready 等待、row conflicts、NoC flit-hop/wire bytes 与最忙链路。
记录增加的 NoC 流量与物理网络预算不变这一事实，平均利用率不代替突发分析。

4-way 若改善，成为日后 Direct HB 的更强 B1 对照；若不改善，按 MC/native/row
记录定位；若 DRAM 分散后转为网络限制，再研究 attachment。不得把单 token
改善推广成全模型推理加速。无新 simulator、BookSim 验收或 RTL 实验。

## 入口

`run_residency_study --output <new directory> --prepare` 固定全部输入和注册。
随后 `--case c0_b1-pair` / `--case c0_b1-four_way` 等使用同一 output，显式传入
既有 `--booksim-source` 与 `--booksim-binary`。各 case 独立日志、结果和完成标志。
运行源码必须与 registration 的 commit 一致；所有构建/测试/实验在 hn072。
