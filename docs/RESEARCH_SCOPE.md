# 固定研究范围

研究适合 repeated-reticle WoW Memory-on-Logic 的有限邻近共享组织：通过静态伙伴和
数据驻留，使变化的需求能够利用存有所需数据的邻近 DRAM 服务；同一份 mapping 再决定
实际需要的并发方向，以 **Configurable Shared Egress** 复用互斥的发送状态。
共享关系可以静态，服务收益仍可动态。位宽按可执行容量与制造成本选择，宽 Home、窄
Shared 是当前候选而非普适原则。Shared 上的常驻字节是完成任务必需的，不能只靠 Home
承诺基础服务；需要联合验证比例、全部必需路径和仲裁。

## Contribution 与 validation

主贡献定位为 **wafer-scale memory-service sharing architecture**。
Configurable shared egress 是实现该架构的机制；RTL、gearbox、FIFO 和 EDA 流程是验证手段，
不单独列为论文贡献。论文收束为两项：有限静态共享组织的任务价值，以及静态 mapping
驱动的服务硬件配置。以下分别记录问题、机制与评估证据：

1. **问题观察**：物理 overlap/connectivity 不等于可兑现的 DRAM 服务。
   固定字节来源、原生服务、endpoint 和共享端口共同决定可用带宽。
   当前代码与反例支持这个机制判断；不据此笼统宣称所有前作忽略了这些限制。
2. **架构机制**：按数据需求和实际完整字容量分配 Home/Shared 的位宽与比例；
   重复模板保留多个合法物理方向，静态伙伴/数据布局提供互斥条件，从而复用 source
   服务硬件。方向选择发生在第一次 HB 之前。等价服务仅针对冻结单伙伴合同，
   不是与 duplicated 的任意动态多方向功能完全等价。
3. **系统组织与评估**：把接口合同、物理连接和静态数据组织放在同一整片 wafer 评估中，
   与 private、k2、独立 k3、full-width direct 做服务—成本对照。
   已完成的是固定 H/plus、注册结构化设计族内的联合选择与评估；
   尚未完成通用 placement 联合综合、真实 workload 或整个 fabric 的全局最优性证明。

RTL 的职责是验证第 2 项能实现、且局部成本没有被模型严重低估。
[单 slice 标准单元结果](reports/ENDPOINT_ASIC_SLICE_REPORT.md) 是其中一层证据；
source 绝对面积差、source 相对差、source 加候选接收端总和分别报告。
不能把特定 `1 source + 3 RX` 的分母推广为整片系统面积，也不能把 2 ns 逻辑时钟
直接套入采用另一原生 slot 校准的 TB/s 模型。

下一系统问题是：**相同逻辑任务在合理静态负载均衡后，有限共享是否减少真正需要的
memory 等待，完整路径成本是否值得？** 用户已指定先完成可验证的导入与回放 infra，
暂无指定真实 trace。固定 H/plus 和已有设计，按[读任务回放合同](methods/READ_WORKLOAD_REPLAY.md)
接对象/地址、冻结布局、依赖、有限请求/返回与任务完成。合成测试不算真实 MoE 效果。
单 slice timing/electrical 修复由独立硬件工作补齐，不再成为推迟 workload 的前置条件。

## 模型职责与边界

| 层 | 职责 | 验证边界 |
|---|---|---|
| Physical opportunity | 重复 reticle、placement、overlap、HB 容量 | 几何可达不代表服务可达 |
| Memory organization | exposure、固定数据驻留、资源竞争 | 数据不能随场景免费替换来源 |
| Service realization | 接口实现及其地址权限、共享资源和容量合同 | FIFO 或多个出口不自动产生聚合能力 |

Matching/cycle 是布局表示和分析工具；endpoint/FIFO 是服务合同的实现与验证组件。暂不独立扩展这些支线，也不加入 thermal、yield、PDN、SI 或复杂运行时调度。

统一方法选择经过验证的接口候选，而不是自由放大服务合同。地址权限 R、物理接收可达性 Y、共享资源容量必须同时成立。一个足够宽的合法单出口也可以兑现共享服务，多出口聚合不是唯一实现。

近期保留两种比较：Home/k2/k3 共用逻辑任务、分别冻结合法驻留，评价服务—成本；
duplicated/configurable 固定同一布局、方向、位宽和请求，评价同服务降成本。
[第一项 FIFO 复用对照](reports/CONFIGURABLE_SHARED_EGRESS_REPORT.md)已完成。
保留 private、k2 direct、独立 k3 和 full-width direct 对照；不先增加 matching/cycle、
任意 k、深 FIFO 或优化框架。小目录最优性不等于全设计空间最优；成本计数不等于 PPA。

[三种接口组织的最新判断](reports/SHARED_EGRESS_ARCHITECTURE_DECISION.md)：FIFO复用保持服务，
存储收益计入pipeline后为4.54%/7.45%；lane与接入长线没有下降，共用发送器未确定占优。
此后按用户明确的source侧方向选择与RX要求，完成[最小TX→HB→RX功能对照](reports/ENDPOINT_ROUNDTRIP_REPORT.md)：
两架构在冻结单伙伴下逐槽等价，全部字逐bit恢复。新增握手/RX之后的payload存储下降23.33%，
lane不变。随后已完成同库同约束的单 slice 映射/STA 与映射后功能回放；
后续物理修复和共同 Home RX 特化已完成，见 ASIC 报告末节；不做 DRAM bank/controller
RTL 或 32-bank 扩展。该 2 ns 局部成本仍须与系统任务模型的供给和频率单独对齐。

完整的新颖性仍需前作全文核对。目录整理及模型诊断本身不作为新的架构贡献。
