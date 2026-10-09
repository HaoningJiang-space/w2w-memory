# Architecture V3 研究范围

研究给已有分布式 Compute Wafer 增加垂直 DRAM 后，原生数据在哪里进入计算网络、
由哪些计算与 SRAM 资源消费，以及由此需要多少横向通信资源。

物理机器、逻辑工作负载、静态放置和运行执行分开。Reticle 是物理区域，
不是计算引擎、SRAM、Router 或 Memory Controller 的同义词。
不同 Gateway 引用同一 DRAM Domain 时共享原生命令、数据与容量预算。

首项研究比较 Central 与 Distributed Vertical Access：冻结逻辑 MoE、权重地址、
计算放置、原生 DRAM、总 HB 数据位宽、总汇聚吞吐与有限缓冲；接入位置、
内部收集线路及控制资源分别进入时间模型和资源账本。External Streaming
是成本单列的参考组织，不是等成本的垂直集成消融。

当前完成的是候选机器上的冷完整层时序与资源代理比较。尚未验证专有产品微架构、
数值推理、暖权重驻留、完整模型性能或真实 PPA；两个架构点不证明全局最优。
旧 Network Design artifact 保留在冻结历史版本，不再生成当前机器。

下一项研究应由已完成结果的限制决定，不预设 endpoint RTL、动态放置、
网络搜索或再次重写 simulator 是必要方向。
