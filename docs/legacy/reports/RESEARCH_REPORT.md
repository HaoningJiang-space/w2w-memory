# Memory-on-Logic：首轮研究结论与复现实验

首轮实验已经完成。结论是：**不能把 reticle radix 的增加直接当作可用 memory bandwidth/capacity 的增加。这个方向是否值得继续，取决于跨接口 bank 共享是否可实现、是否有足够带宽以及成本是否可接受。**

## 实际完成的工作

- 服务器：`wangziheng@eex005`，目录 `/home/wangziheng/Video/w2w-memory`，CPU affinity 为 0–3。
- 实验代码：`b067e66b13aa9b06806dd7af88abca67abf06237`，分支 `research/memory-on-logic-gate`；实验开始时本地和远端提交一致，远端工作区干净。
- 原始上游：`9470042fb2d8b5368556e46cc75ac818dbf31522`，保留原 origin。代码通过 Git bundle 同步，没有对公共上游发布。
- 8 项测试通过；原论文 24 个拓扑重建完成；11,776 次线性规划求解完成，退出状态为 0。
- 扫描 200/300 mm、4 种布局、2 种 bank 语义、4 档 HB 预算、2 档 controller 预算；pooled 接口另有 3 档服务能力。随机活动使用 10 个种子，并有单点、集中活动和全负载对照。
- 实现 `memory_and_logic`，显式 `memory_endpoint`，正交的 memory 分析入口及针对不支持的 BookSim/Orion 路径的保护。

## Gate 0：复现结果及口径

对照 [论文 Table 1](https://arxiv.org/html/2603.05266v1)，24/24 的 compute/interconnect 数、直径、两位小数平均 hop 一致。不是完整 BookSim 性能复现。

4 个 LoI Interleaved 配置的几何图最大 compute degree 都是 3，论文标称 radix 是 4。`plots.py:create_overview_table` 使用硬编码 radix 字典，并非从几何邻居计算该列。本次同时保留标称值和实测值，未修改 geometry 来迎合表格。

二分带宽使用 10 次 METIS 启发式分割。本次与论文表格的最大绝对差为 2.40（表格带宽数值口径）；不声称逐位复现。原代码邻接表重复插入反向边，原始 cut 数与 2 TB/s 每条唯一链路的换算存在数值上的抵消，不能再把原结果乘 2。输出额外给出唯一链路 cut 与换算值。

## Gate 1：用 bank 可达性校正 reticle 可达性

公平对照使用相同 compute 坐标、相同 C/M 数、reticle 面积、四接口模板和总 HB 预算。200 mm 是 12+12 reticles；300 mm 是 36+36。Aligned、X 半移位、XY 半移位只改变 memory 位置。为避免裁切不同 reticle 数，三者统一预留边缘空间，因此这不是最大 wafer 利用率方案。

默认每个 full-size memory reticle 有 16 GiB、1 TB/s DRAM 服务能力；每个 C/M 的 HB 总预算为 4 TB/s，compute controller 为 4 TB/s。这些是用于判断机制的假设参数，不是某款 DRAM 的实测指标。

| 内部 compute 的布局 | memory degree | 本地 bank 分区可达容量 | 理想整颗 memory 可达容量 |
|---|---:|---:|---:|
| Aligned | 1 | 16 GiB | 16 GiB |
| X half-shift | 2 | 16 GiB | 32 GiB |
| XY half-shift | 4 | 16 GiB | 64 GiB |

分区情况下，每个接口只能服务自己拥有的 1/4 banks。一个 compute 从“一颗完整 memory”变为“四颗 memory 各 1/4 banks”，因此容量与内部 bank 带宽不增加。边缘节点的可达容量还会减少。共享的可达容量不能跨 compute 求和后当作系统总容量。

`C—M—C` 是结构图上的路径，不是合法的转发通路。当前模型不把 DRAM 作为 router；memory request 仅允许一条直接 HB 边，不支持全局远端地址访问。

## Gate 2：实际数字

以下均为 **300 mm、相同 36 C + 36 M、HB/controller 各 4 TB/s、每颗 memory 1 TB/s**。数值是每个 active compute 的平均服务带宽上界，单位 TB/s；随机负载对 10 个种子取均值。每个 active compute 需求为 4 TB/s，数据假定可在可达 memory 中自由放置。

| 接口模型 / 活动模式 | Aligned | X half-shift | XY half-shift |
|---|---:|---:|---:|
| 本地 bank 分区 / 单个内部 compute | 1.000 | 1.000 | 1.000 |
| 本地 bank 分区 / 随机 25% 活动 | 1.000 | 0.939 | 0.867 |
| 本地 bank 分区 / 集中约 25% 活动 | 1.000 | 1.000 | 1.000 |
| 本地 bank 分区 / 随机 50% 活动 | 1.000 | 0.914 | 0.828 |
| 本地 bank 分区 / 全部活动 | 1.000 | 0.917 | 0.840 |
| 理想整颗 bank 共享 / 单个内部 compute | 1.000 | 2.000 | 4.000 |
| 理想整颗 bank 共享 / 随机 25% 活动 | 1.000 | 1.678 | 2.467 |
| 理想整颗 bank 共享 / 集中约 25% 活动 | 1.000 | 1.333 | 1.889 |
| 理想整颗 bank 共享 / 随机 50% 活动 | 1.000 | 1.439 | 1.828 |
| 理想整颗 bank 共享 / 全部活动 | 1.000 | 1.000 | 1.000 |

XY half-shift 在理想共享、随机 25% 活动下是 aligned 的 2.47 倍；10 个种子的每 active compute 带宽范围为 1.778–2.778 TB/s。这是模型内的服务上界收益，不能表述成应用加速。

![300 mm 服务上界比较](../../memory_results/eex005_gate/comparison_300.png)

全负载下，分区模型从 aligned 的 36 TB/s 降至 XY half-shift 的 30.25 TB/s（下降约 16.0%），原因是有限阵列边缘未配对接口。在理想共享模型下，两者都是 36 TB/s，geometry 没有增加总 DRAM 服务能力。

Controller 限制为 1 TB/s 时，单点的 4 倍收益消失。HB 总预算降至 1 TB/s 时同样消失。即使地址可达整颗 memory，将每个 memory 接口的服务限制为该 reticle 的 1/4 带宽，也会消除内部单点的增益；接口能力提高到 1/2 才能得到中间收益。完整扫描同时记录 throughput 最大化和共同完成比例最大化，避免仅报告聚合带宽而掩盖不公平。

Rotated 的最大 memory degree 达到 7，且几何检查通过；但 200/300 mm 对应 20+20、48+48 reticles，与上述匹配对照不等资源。它使用面积更小的 memory reticle，模型按面积缩放 DRAM 带宽和容量。结果保留用于探索，不将它对 aligned 的差异直接当成公平 speedup。

## 对 research question 的修正

建议把核心问题写为：**在重复 reticle 模板、固定 HB/controller 预算以及局部 bank-to-port 连接限制下，怎样协同设计 bank 共享范围、HB 接口和相对 placement，以改善不均衡 memory demand 的有效服务能力？**

原来的 placement → overlap → topology 主线仍有价值，但必须补上一层 bank-to-interface connectivity。否则把 memory 当成能免费选择所有 banks 的端口，会制造虚假的收益。对于四个均分接口，若一个 compute 仍只能连接四组独立 banks，degree 提升不改变内部节点的资源上限。

当前 gate 判断：**“只将原 repo 的 interconnect 改名 memory”不成立；“在有限共享成本下回收闲置 bank 带宽”值得做下一轮可实现性验证。尚未证明具有论文贡献或真实 workload 收益。**

## 下一轮实验的具体优先级

1. 先定义可实现 bank 共享接口：例如 32 banks、4 个 HB 区域，每个 bank 可由 1/2/4 个区域访问。逐 bank 建立 ownership、读写服务和仲裁约束，估算额外 mux/crossbar、长连线和控制代价，不能只扫一个免费 pooled 参数。
2. 加入容量约束和静态数据布局：同一组 pages/experts/tensors 在所有方案中固定大小，placement 决定能否被任务访问。比较迁移前后的收益并计入迁移流量，禁止每轮请求重新“免费选最空 memory”。
3. 选能观察到不均衡活动的真实请求 trace，检查活动比例、bank 热点和空间聚集。联合 task/data placement，比较均匀、聚集与稀疏阶段的净收益；不要先用人工单点活动代表应用。
4. 将等资源对照与最大 wafer 利用率对照一起报告；在有限共享下确认收益后，再接 DRAM timing。第一阶段继续排除 thermal/yield/PDN。

若收益只存在于免费全 bank pooling、自由数据重排或很低活动比例，且实现成本无法支撑，就应停止这个版本的研究方向。若有限共享仍有可重复收益，再进入 timing 与物理成本模型。

## 技术证据边界

[Micron WoW 披露](https://patents.google.com/patent/US20240420757A1/en) 包含 memory/logic 接口、LIO/sense-amplifier 相关 transceiver，以及 256K 数据连接、1.2 μm pitch 的例子。这支持细粒度 bank/periphery 接口值得建模，但不证明本实验的跨 reticle 全 bank pooling，也不是这里带宽参数的校准来源。

本实验只检查 reticle/connector 几何区域。没有 pad-level 信号对准、制造设计规则验证、实际 DRAM 时序、refresh、row locality、读写反转、延迟或能耗结果。图中数值是 fluid LP 上界。

## 复现与产物

- [模型与命令说明](../guides/MEMORY_README.md)
- [Memory 模型](../../w2w/geometry/memory_model.py)、[扫描入口](../../w2w/experiments/run_memory_experiment.py)、[Gate 0 入口](../../w2w/experiments/run_gate0.py)
- [原始 Gate 0](../../memory_results/eex005_gate/gate0.json)、[全部 memory 结果](../../memory_results/eex005_gate/memory.json)
- [图表汇总数据](../../memory_results/eex005_gate/summary.json)、[执行日志](../../memory_results/eex005_gate/experiment.log)、[环境版本](../../memory_results/eex005_gate/environment.txt)
- 远端完整目录：`/home/wangziheng/Video/w2w-memory/memory_results/eex005_gate`。
- Git 跟踪本报告及精简结果 `artifacts/results/baseline/research_results.json`；大批量原始输出保存在上述本地/远端结果目录。
