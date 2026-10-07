# Memory service provisioning 的研究判断与形式化

2026-10-08补充：[完整返回路径研究](../reports/RETURN_PATH_PROVISIONING_REPORT.md)已完成166次新回放。
它将本页的共享状态约束落实为TX打包/RX占位周期合同，并在独立routing输入上验证冻结比例。
下文引用的旧执行数量、收益及“尚未回放”描述保留为此前分析时点；最新结果以补充报告为准。

研究主线保持为：在重复 reticle 的 WoW 系统中，组织服务接口、物理连接和静态数据，
利用已有闲置 DRAM 服务。将 endpoint 泛化为静态可配置 service fabric 是值得验证的
架构假设；三张图的命名本身不构成新贡献。本分析合入 `11fd2ab` 的最新比例推导，并核对此前 `ce549ce` 的真实回放与物理归档，
下面的 engine pool、命令时序后端和联合优化模型尚未实现。

## 当前实现与新提案的距离

`domain/endpoint.py:EndpointSpec` 的共享 FIFO 是 bank-local。
`domain/design.py:MemoryFabricDesign.shared_directions` 为每颗 memory 实例冻结一个方向；
布局中的每份数据必须通过唯一合法路线，且不能使用未选共享方向。
因此当前是 **每 bank 一个 Shared TX，多个 bank 仍有各自的状态和服务能力**。
它不是整颗 reticle 一个 engine，也没有实现多 bank 共用一个中心 engine pool。

应区分三个设计族：

| 设计族 | 额外要解决的问题 | 当前证据 |
|---|---|---|
| 同 bank 的方向状态静态复用 | 一次部署只需一个共享方向时，删除重复发送状态 | 已有执行与局部 RTL/P&R |
| 同 bank 的少量 engines 支持多个目的地 | 静态 binding 的粒度、哪些方向同时占用 engine | 待建模 |
| 多 bank 共用 engine pool | 汇聚网络、吞吐、仲裁、返回 ID、credit、跨 bank 连线 | 新架构，待实现 |

先研究小 bank group 或 bank-local engine provisioning，可以复用现有实现。
若直接引入 reticle 中心 pool，节省的 FIFO/serializer 可能被汇聚线与仲裁抵消。
同一模板能选择 Left 或 Right，不意味着同一部署能同时向两个方向提供完整服务。

## 现有结果支持到哪里

当前局部物理结果必须使用修复后的口径：source 面积
21,987.294 → 15,318.674 μm²，减少 30.33%；包含相同 Home RX 和两套 Shared RX 的
路径合计 46,023.320 → 39,354.700 μm²，减少 14.49%。这是 Nangate45 单角局部结果，
不是整片、DRAM 工艺或功耗。见 [物理报告](../reports/ENDPOINT_ASIC_SLICE_REPORT.md)。

九个 N192 读窗口中，定义宽 k3 相对 Home 的增益保留率：

\[
\eta_w=\frac{T_H/T_B-1}{T_H/T_{k3}-1}.
\]

从[归档 CSV](../../artifacts/results/workload/patterns_replay/replays.csv)直接重算：

| 窗口 | 额外加速保留率 |
|---|---:|
| g0/g1/g2 的 batch1 | 56.00% |
| g0/g2 的 batch4 | 62.92% / 62.93% |
| g0/g1 的 batch16 | 69.01% |
| g2 的 batch16 | 65.63% |
| g1 batch4 | 不定义，参考设计没有正收益 |

不能用绝对性能比替代增量收益比而不说明分母。宽 k3 也只是冻结的配对设计，
不是 full pooling oracle。B 减少 lane/bit-mm，却增加 payload buffer，不能把单项
节省直接解释为总体成本优势。k2 在多个窗口与宽 k3 同速，是必须保留的强参考。

当前可以说方向复用节省了可测状态，真实 routing 驱动的读阶段存在共享机会；
还不能说以很小整片成本保留了几乎全部共享收益，或已经形成普遍 Pareto 优势。

## 最新比例结果已经给出更具体的方向

已合入的 [service provisioning 实验](../reports/SERVICE_PROVISIONING_REPORT.md) 将请求容量 N 与完整字生命周期纳入静态比例推导。N128 下 A/B 都选 Home=4/5，189 次合成回放中分散完成分别从 79/77 降为 73 槽；较窄 A 与 B 同速。N192 下旧 B 仍更快。新比例尚未在真实 routing 上执行，不能把它当作新的真实 workload speedup。

它说明下一步可以先选择“位宽、请求容量、驻留比例”，无需立即增加跨 bank engine pool。这个方向已有构造和执行证据，优先于为扩大题目而引入新互连。

另一项容量界尤其重要：按每 engine 5/8 word/slot、固定 Home=8/13，32-bank memory 要维持 32 words/slot，至少需要 20 个 shared engines；达到 52 words/slot 目标至少需要 32 个。将 32 个 bank-local engines 改称一个 reticle engine 并不会节省带宽需求。一两个 engine 的提案必须先说明它们是否相应变宽，以及聚合互连的成本。

## 三张图需要再加一个共享资源模型

物理图 G_P 表示合法 HB 路线；驻留图 G_D 表示字节的固定来源；服务图 G_S 表示
可用导出路径。但 G_S 仅给独立边容量还不够：两条边可能共享一个发送器、bank、
port 或请求队列。若把它们拆成两条独立满速边，会再次复制服务能力。

静态 binding z 下的流体合同应写成：

\[
\mathcal S_\tau(z)=\{f\ge0:\ f\text{ 只使用合法地址及物理路径},\quad
 D_\tau(z)f\le q_\tau\}.
\]

其中 D 的行表示共享 bank、engine、HB、controller 等资源，列表示真实流。
FIFO 容量、突发、请求依赖与 DRAM 状态需要执行模型；不能由一个无状态多面体
完整表达。流体合同用于上界和选择，有限执行用于判断是否兑现。

地址权限与物理可达性必须取交集。让地址能从两个出口返回，并不意味着这两个
出口都连接到同一 compute；多出口聚合不能跨越不存在的 overlap。

## 哪些变量静态 哪些行为动态

设 H 为重复制造模板，包括 bank-to-engine 支持、engine 数/宽度、HB 接口和缓冲。
每个 memory 实例有部署时 binding z_m。数据驻留 A 在测试前冻结。
运行时允许队列、仲裁和服务速率变化，不允许按活动集合重选 z 或 A。

“静态”必须声明时间范围：若覆盖所有模型层，binding 必须支持所有驻留层的方向
需求并集；逐层换 binding 是另一种机制，需要配置时间、状态排空和地址合同。
不能给每个窗口单独生成最省 engine 的配置，却称它为一个部署。

重复模板约束的是 H，并不要求不同实例的数据比例或 z_m 相同。
模板成本只计一次设计类型，但物理资源必须按实例数量和边缘实装分别计数。

## 有用的优化问题

先固定合法几何 g，再选择 H、静态 z 与 A。以有限读阶段的完成时间为目标：

\[
\min_{H,z,A}\ \sum_w p_w T_w(H,z,A;g)
\quad\text{s.t.}\quad C(H,g)\le C_{\max}.
\]

同时约束真实存储容量、地址可达、共享服务、HB/controller、模板重复和有限
请求状态。必要时加入退化界或分位数约束，但不默认所有研究都必须严格保底。
geometry 外层只需先比较少量既有合法方案，不必发明新 H/plus 轮廓。

另一种更易解释的目标是最小化成本，同时达到规定的完成时间/收益保留率。
收益接近零的窗口直接报告时间差，不计算不稳定的增量比率。不要把面积、能耗、
wire proxy 混成未经标定的一个 C；先按多个成本坐标报告前沿。

### 固定字节的完成时间模型不必一律是非凸

速率目标中的 A*r 确实双线性，但不是所有 formulation 都需要这样写。
设窗口 w 的对象 o 已知读取 D_ow 字节，a_ob 为其在 bank b 的固定字节比例；
F_obp,w 为经合法路径 p 交付的总字节。则：

\[
\sum_p F_{obp,w}=a_{ob}D_{ow},\qquad
\sum_{o,b,p}d_{\rho,obp}F_{obp,w}\le q_\rho T_w.
\]

这里 a*D 适用于完整对象读取或明示的均匀条带访问；若窗口只读取某些地址，必须
细分为地址类并固定各类需求，不能用整对象容量比例替代实际读取比例。

D 已知、路径与 q 固定时，上述约束对 a、F、T 都是线性的，容量约束
sum_o a_ob*size_o <= capacity_b 也线性。因此允许连续 striping 的共同完成时间
流体放松可直接是 LP；不必先用 SLP 处理 A*r。

它假定窗口字节均可服务、忽略 release/依赖/有限队列和状态时序，是完成时间的
乐观参考，不是现有逐字回放的替代。任意 sum-throughput 目标仍可能非凸。
若 q 也连续可变，q*T 又出现乘积；可先枚举硬件合同，或用有限配置选择形成 MILP。
有共享 engine 的配置不能只把各局部独立最优值相加，必须保留全局耦合约束。

## Complementarity 应通过服务反事实衡量

两两相关系数忽略字节大小、容量和尾部；min(idle_i,demand_j) 也只是潜力代理。
其中 demand 应是同一时间窗内未满足的服务需求，单位应与 idle 一致，并且这些
字节真的驻留在 i 可供应的位置。否则“有空闲”不能转化成“能提供缺失字节”。

小规模选择可以直接计算同一窗口、同一成本下有/无共享的完成时间差。
pair 权重可作为启发式，多个共享组存在 bank/engine 竞争时不能保证可加。
当前 trace 分析主要证明稀疏占用机会，尚未证明普遍强负相关。

## 能区分架构价值的最小实验

1. 固定 g、A、请求供给与总 lane/HB 容量，比较 dedicated、静态删去未用方向的
   dedicated 强基线、少量 engine binding。先隔离状态复用，不同时缩宽或改布局。
2. 用一个 bank 两个目的地、一个 bank 多目的地同时需求、两个 bank 共用一个
   engine 三个小构造，核对绑定合法性、串行瓶颈、反压与字节守恒。
3. 对有价值的设计再优化 A；分别报告 binding 单独收益、layout 单独收益和联合收益。
4. 对完整路径做同成本与同完成时间比较，保留 Home、优化 k2、宽 k3 和放松上界。
   configurable 节省状态并不自动节省 HB pad、所有方向长线或 RX。
5. 用新保留的 requests、层/步与 batch 分布检验泛化。train 用于拟合选择，val 用于
   选择超参数，test 只用于最终评价；三者不训练 LLM。当前看过的窗口不能再算未见测试。

负对照应是 bank 服务实际平衡饱和的需求，不只是所有 compute 都 active。
饱和时没有可借服务；新设计可能相同，也可能因配置不足而退化，都应报告。
更大 batch 的专家复用、缓存、读取次数与 token compute 要作为显式执行假设。
读阶段完成比不能直接代替端到端 token 加速。

## DRAM 时序与物理实现的验证层次

公开 DRAM 命令模拟器应通过接受请求/推进时间/完成回调接口接入，支持地址映射、
ACT/PRE/RD、bank group/channel 竞争和刷新。原生完成后仍受 endpoint/HB/RX 限制；
要预留有限返回容量，避免 DRAM 完成数据凭空丢失或无限积压。固定延迟或周期
ready pattern 不等于真实 DRAM 时序。公开 HBM 模型也不等于定制 WoW bank 的工艺证明。

PPA 先复用已提取的局部块，逐项补绑定网络、请求状态、长线/HB、clock/RX。
hierarchical 估计必须标明缺项与范围；片上网、PDN、HB/DRAM 工艺和多角签核不能
靠将 cell area 乘以 bank 数解决。真实 signoff 需要实际工艺、宏、顶层设计与规则。
目前仅有局部公开平台证据，新的命令时序与整片 signoff 都未完成。

## 新颖性应该落在哪里

最有潜力的是重复模板下“可连接方向”与“需要同时配置的服务硬件”分离，且以
完整成本证明何时少量 engines 足够。三个图、static mux、matching 或加权 striping
单独都不足以构成新贡献。即使收益成立，仍需和已有接口复用与资源配置方法比较。

[MoEntwine](https://arxiv.org/abs/2510.25258) 已研究 wafer-scale EP 的映射与迁移；
[Patterns Behind Chaos](https://arxiv.org/abs/2510.05497) 同时包含 routing 分析与
wafer-scale 架构案例；[Stratum](https://arxiv.org/abs/2510.05245) 做 3D DRAM 与
MoE serving 的系统硬件协同；[H2EAL](https://arxiv.org/abs/2508.16653) 也包含 HB
架构和 memory/compute co-placement。不能概括为“前人都只在固定硬件上调度”。
这些范围对照不等于完成了新颖性检索；尤其不能仅靠 SiloBreaker 发表记录排除重合。

最终贡献应由实验决定：若只对单一冻结 pair 删除一个未用方向，工作仍可能只是
局部 right-sizing；若重复硬件能适配多种静态驻留，在完整成本下维持服务，并且
geometry 会改变最优配置，才更接近一个可推广的 wafer-scale service architecture。
