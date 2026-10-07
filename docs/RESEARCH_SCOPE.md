# 固定研究范围

研究适合 repeated-reticle WoW Memory-on-Logic 的低成本共享 memory interface，使邻近
compute 能利用已有的闲置 DRAM 服务。当前主候选为 **Configurable Shared Egress**：
宽 Home、窄 Shared、冻结方向选择和匹配的静态数据比例，利用配置互斥减少重复服务硬件。

| 层 | 职责 | 验证边界 |
|---|---|---|
| Physical opportunity | 重复 reticle、placement、overlap、HB 容量 | 几何可达不代表服务可达 |
| Memory organization | exposure、固定数据驻留、资源竞争 | 数据不能随场景免费替换来源 |
| Service realization | 接口实现及其地址权限、共享资源和容量合同 | FIFO 或多个出口不自动产生聚合能力 |

Matching/cycle 是布局表示和分析工具；endpoint/FIFO 是服务合同的实现与验证组件。暂不独立扩展这些支线，也不加入 thermal、yield、PDN、SI 或复杂运行时调度。

统一方法选择经过验证的接口候选，而不是自由放大服务合同。地址权限 R、物理接收可达性 Y、共享资源容量必须同时成立。一个足够宽的合法单出口也可以兑现共享服务，多出口聚合不是唯一实现。

近期问题：相同 placement、数据与 workload 下，独立复制 shared endpoint 与可配置
shared endpoint 怎样交换服务和硬件成本？[第一项 FIFO 复用对照](reports/CONFIGURABLE_SHARED_EGRESS_REPORT.md)
已完成。保留 private、k2 direct、独立 k3 和 full-width direct 对照；不先增加 matching/cycle、
任意 k、深 FIFO 或优化框架。小目录最优性不等于全设计空间最优；成本计数不等于 PPA。

完整的新颖性仍需前作全文核对。目录整理及模型诊断本身不作为新的架构贡献。
