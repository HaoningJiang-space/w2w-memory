# Shared Egress：先确定架构收益，再进入物理实现

2026-10-07；模型补充验证源码 `3c60583`，eex005。

**当前可确认的是：冻结共享方向能消除重复 FIFO，保留同位宽独立出口的服务。
目前没有减少两条物理方向、lane、HB 或长线，也未证明完整硬件成本占优。**
按用户最新安排，停止继续 RTL/综合工作，先依据下面的执行服务和成本向量判断架构。
本次已提前完成的小型 endpoint 原型保留在附录，作为探索证据；不据此启动下一阶段。

## 1. 三个组织方式，保持同一份工作

三者都保留 H/plus、36C+36M、32 banks/M、18 对、96 条重复模板连接、相同原生服务、
静态字节布局、接口位宽和活动集合。每个 memory 的方向在完整布局冻结时设置；运行时不切换。

| 组织 | 每 bank 的 Shared 存储 | 发送器 | 方向选择位置 |
|---|---|---|---|
| 独立出口 | 每方向一个 FIFO | 每方向一个 | 分派到各自 FIFO |
| 共用 FIFO | 一个 FIFO | 每方向一个 | FIFO 与发送器之间 |
| 共用 FIFO＋发送器 | 一个 FIFO | 一个 | 窄 beat 产生之后 |

Home 和 Shared 是原生分派后的并行分支，不是串行经过的两级。
方向选择和序列化都在 memory 侧、长接入线和首次 HB 之前；HB 之后直接到合法 compute。
两个方向的 driver、长线、流水寄存器和 HB 均保留。

只要所选方向冻结，空闲分支一直为空，将其删去不改变已有队列的准入与发送状态转移。
这一等价性依赖固定单伙伴布局；不能用于一个实例同时服务两个 Shared 方向的情形。

## 2. 模型已经回答的服务与成本

下表每行为完整制造模板的每-M计数；服务是均匀恰好 9-of-36 的精确期望，单位 TB/s/active C。
所有设计满载每 C 都为 1。Wire 是已建模的 bank-to-port 接入线，不含长度未知的局部选择接线。

| 设计 | 平均服务 | Endpoint bits | Pipeline bits | Lane bits | Access wire bit-mm |
|---|---:|---:|---:|---:|---:|
| Home direct | 1.000000 | 8,192 | 63,488 | 8,192 | 120,832.0 |
| k2 direct | 1.327731 | 8,192 | 126,976 | 16,384 | 241,561.6 |
| A，独立出口 | 1.385714 | 24,576 | 155,904 | 16,384 | 297,497.6 |
| A，共用 FIFO | 1.385714 | 16,384 | 155,904 | 16,384 | 297,497.6 |
| A，共用 FIFO＋发送器 | 1.385714 | 16,384 | 155,904 | 16,384 | 297,497.6 |
| B，独立出口 | 1.482143 | 40,960 | 179,008 | 18,432 | 341,664.0 |
| B，共用 FIFO | 1.482143 | 24,576 | 179,008 | 18,432 | 341,664.0 |
| B，共用 FIFO＋发送器 | 1.482143 | 24,576 | 179,008 | 18,432 | 341,664.0 |
| k3 full-width direct | 1.771429 | 8,192 | 248,320 | 24,576 | 474,163.2 |

A：256/128/128 bit，D=1/1/1，home 比例 2/3。
B：256/160/160 bit，D=1/2/2，home 比例 8/13。
Direct 的 8,192 bits 是每 bank 一个原生字寄存器，不能忽略。

相对同位宽独立出口，A/B 的 endpoint 存储下降 **33.3%/40.0%**；
endpoint+pipeline 两项存储合计下降 **4.539%/7.448%**。共同发送器没有进一步减少这两项。
选择器、控制、局部接线的代价还须单列，因此这些结果是已计成本维度的改善，尚非完整 PPA Pareto 证明。

也应区分两个参照：相对同位宽独立出口，服务保留100%；相对 full-width direct 超过
private 的增量服务，A/B 只回收 **50%/62.5%**。不能把后者描述为接近全部共享收益。
相对 k2 direct，A/B 平均服务提高约4.37%/11.63%，但 endpoint 存储为2倍/3倍，接入
wire 多23.16%/41.44%。因此保留 k2 的低成本前沿，不预先认定可配置 k3 是总赢家。

## 3. 发送器数量不能直接作为成本

共享发送器把每 M 的窄发送器数从64减到32，选择器移到128/160-bit beat之后。
其局部成本取决于发送器、FIFO和分支点的相对位置，以及跨完整字尾部的实现。

在整 beat ready/stop、256-bit 原生字的本次实现中，FIFO-only 方向选择需要可见的位数是：

\[
V=W+\begin{cases}w-\gcd(W,w),&D_S\ge2,\\0,&D_S=1.\end{cases}
\]

B 的160-bit发送会跨越当前字尾和下一字的前128 bit，因此 V=384；A 的 V=256。
这修正了前轮示意图对 B 局部总线仅按256 bit计的简化，不修改历史归档。
它是本次 packetizer 组织的计数，不是所有 serializer 的最小电路定理。

| 候选 | FIFO-only 选择器输入 bits/M | 共用发送器选择器输入 bits/M | 窄发送器数/M |
|---|---:|---:|---:|
| A | 8,192 | 4,096 | 64 → 32 |
| B | 12,288 | 5,120 | 64 → 32 |

每个选择器有两个物理输出，合计输出位数为表中输入的两倍；不能把输入位数当作整个电路面积。
若 FIFO 到两套发送器距离为 l1、l2，共用发送器距离 FIFO 为 a、到两个分支点为 b1、b2，
局部数据线代理分别为 V(l1+l2) 与 Va+w(b1+b2)。只有后者更小才有这段 bit-mm 收益。
目前没有这些坐标，局部接线保留未知，不计零，也不报实测下降。

## 4. 本轮模型验证与当前决策

原 FIFO 复用验证为 `7604acb`：22测试、441 LP、12次配置轨迹比较。
补充 `3c60583`：23项定向测试通过；两个共用发送器候选各21个冻结活动场景、
各3个LP，共126 LP。逐客户端服务和公共完成率与原 FIFO 复用归档差为0，
最大资源残差3.66e-15；每个候选的布局哈希及冻结方向已记录。
全局组合仍使用已有峰值容量证书，不包含链路延迟仿真或真实 DRAM timing。

**保留的架构骨架**是宽 Home＋窄 Shared、静态方向选择、匹配的数据份额；
共用 FIFO 是已验证机制，共用发送器保持为可选实现，不能凭模块数量将其设成默认优胜者。

近期只回答：在强基线和完整成本向量下，这份共享收益值不值得新增硬件。
先用当前数据保留有意义的预算区间和目标服务点，并把未计的局部成本写成明确条件；
不重新扫描 FIFO，不增加 placement，不引入新搜索框架。
当架构比较支持继续且接口契约稳定以后，才为新增端点块做小 RTL 与库映射/PPA；
不实现 DRAM bank/controller 或整个 wafer。

## 5. 最新合同核对：gearbox、接收重组与物理位置

用户最新补充把后续RTL问题收敛为：完整字接口的持续服务是否能经由有限队列、跨字拼接、
物理链路与接收重组端到端兑现，以及付出的局部实现成本。当前仍不扩RTL或启动PPA。

### 5.1 当前源码已经验证什么，还缺什么

| 项目 | 当前源码事实 | 后续需要验证的内容 |
|---|---|---|
| 跨字packing | `cse_packetizer` 使用 `{next_view, head_view}` 与phase移位，160-bit会同时读取前字尾与后字头 | 饱和、突发、有限尾部、停顿条件下的TX→RX完整字正确性 |
| 192-bit | Python执行支持；本次RTL只运行128/160、Home固定256 | 192 D1的0.5与D2的0.75必须实测，不能算入既有144次验证 |
| 输入目的地 | RTL从外部 `in_dest` 接收，内部没有周期流量生成器 | 正式接口改为映射提供的role/必要metadata；周期比例只在testbench中 |
| 输出握手 | `units` 由 `ready` 门控，表示当槽实际发送的32-bit单位数；没有独立`out_valid` | 若采用ready/valid，`valid && !ready`时数据、有效位数、metadata保持，直至握手 |
| 输入握手 | 当前随机激励可在未握手时撤销valid；非法方向测试会换dest | 不能把这组slot-offer激励称为标准valid/ready协议验证；后续激励也要遵守hold规则 |
| 接收端 | oracle按端口比较发送token序列及哈希，无RTL receiver | 接收gearbox、完整字输出背压及其逻辑/存储成本 |
| 布线与时序 | 未建模链路延迟、ready往返或库时序 | 长线credit延迟需要的存储/流水；统一时钟下的局部STA，不能从零延迟credit推定 |

上述credit接口有自己的明确语义，并不因缺少ready/valid而自动错误；但不能直接宣称已经
满足用户要求的“停顿时valid/data保持”。后续若增加holding/skid寄存器，必须计入存储、
延迟和服务验证，不能把它藏在D之外后继续声称相同成本。

对无限持续流，192-bit的对齐周期为3个256-bit字/4个beat；160-bit为5字/8beat，
128-bit为1字/2beat。这些是饱和数据线利用率，不保证有限对象、缺字或背压下仍达到相同速率。
有限流尾不足一个beat时，要定义有效单位数及flush；否则RX可能永远等待下一字。

### 5.2 后续只定义一个read-return合同

输入为已经合法产生的256-bit读返回及其原始role；endpoint不调度DRAM命令、不生成数据目的地。
`native_valid && !native_ready`期间由源保持data和role。若上游DRAM返回本身不可停顿，
需要在发起读时预留接收容量或显式上游response buffer；不把ready反压当成能取消已完成的读。

输出选定明确的beat协议。若使用ready/valid，停顿时保持payload、有效单位数和metadata；
配置在一个运行epoch内冻结。第一版每个源—目的流有序，接收端恢复原始完整字，debug tag
用于scoreboard；真实协议若需要request ID、bank ID或帧边界，它们的传输与存储另计。
不能允许跨不同目的流拼接而省略流标识。

TX、链路、RX共同检查唯一有效payload守恒：

\[
256N_{accepted}=256N_{RX\ delivered}+U_{TX}+U_{link}+U_{RX}.
\]

U分别为各段尚未交付的有效位，互不重计；FIFO中已发送的前缀即使物理寄存器还在，也不
再次算作待交付位。另查每个tag仅接收一次、FIFO容量、顺序和错误方向静默。
重置时清空一个epoch，配置只允许在reset/空闲边界改变，不把reset丢弃与正常守恒混用。

后续功能证据应为 `accepted native words == reconstructed RX words` 的逐字逐bit比较；
独立byte/token scoreboard避免仅镜像Python控制逻辑导致同源错误。
接收端至少作为验证模块，且TX/RX与有效单位/握手控制均进入端点成本。不同compute处的RX
不能因发送侧共享FIFO就自动合并。

### 5.3 Logic-side是物理候选，不能直接套原成本和可达性

[Micron US20230048628A1，Figs.3F–3G及相应说明](https://patents.google.com/patent/US20230048628A1/en)
披露了logic侧transceiver与sense-amplifier/LIO耦合的组织，支持研究这种分层。
这是专利结构披露，不是本候选的PPA实证。
但[当前沿用的WoW网络假设](https://arxiv.org/html/2603.05266v1)禁止同层reticle直接互连。
因此本项目的连通性推论是：完整字先经HB进入C0之后，C0内部的方向选择器不能自动把它送给C1。
必须明确另一个合法跨层路径、改变拓扑假设，或保留HB之前的方向选择；都不能免费替换原图。

本次旧模型仍是假定memory侧数字外围在长线/HB之前完成序列化；不能仅以普通logic库综合
就宣称它已合法放到logic层。可先对与层位置无关的数字功能作局部比较，系统成本和可达性
则在确定端点落点后重新检查。若宽字先跨HB，窄serializer不会倒过来节省前段HB宽度。

成本分别报告TX-local、RX-local、控制/metadata、pipeline、wafer接入线和HB；
RTL寄存器与旧proxy重叠时替换对应条目，不能相加两次。面积、存储位、bit-mm和能量保留
为各自维度；有一致单位的映射后才能合成总成本。
现有 `fixed_sequence_control_bits` 是周期请求源的ROM/cursor代理，不是该RTL含有sequencer
的证据。正式端点由外部role驱动时，应将这项归到源请求模型或移除，改计实际metadata/control；
不能同时按流量ROM和真实端点控制收费。

### 5.4 架构值得继续后，才做的有限验证

第一步仅single native source slice＋验证用RX，不实现array、controller、NoC或整个wafer。
只保留四个系统组织：256-wide direct强基线、192等宽buffered、256/160独立出口、
同宽同数据的configurable shared。192 D1/D2、两路128和有限流尾部作为gearbox功能测试；
128的单模块正确性不能代替完整A方案的PPA。如果要比较A/B硬件最优性，届时需显式纳入A。

等宽192与256/160使用各自冻结数据比例；唯有后两项严格保持宽度、数据和workload相同，
单独归因共享组织的收益。Wide direct应保留既有单原生字holding-register语义，不能换成
三个独立全宽FIFO后仍称同一个低成本基线。

先验证payload、握手和RX，之后才在同库、同时钟、同约束下比较局部面积/时序；功耗必须
使用实际活动与相同有效工作量。32-bank汇聚只在single-slice结果值得继续且资源/metadata
合同清楚后开展，32倍逻辑计数不能代替聚合与扇出验证。当前不安装OpenROAD或运行这些步骤。

## 附录：已提前完成的探索性原型，后续暂停

为了完整保留本次执行历史：`rtl/cse_bank.sv` 与 `cse_tb.sv` 已完成一个小型 endpoint 原型。
它包含 FIFO、分派、32-bit单位的 packetizer、方向选择和 ready/stop；没有 DRAM阵列或控制器。
源码 `3c60583`，Yosys/Icarus 版本、输入哈希和原始统计见归档。

6种配置（两宽度×三组织）、每种12条输入，在RTL及generic gate网表各运行一次，
共144次仿真、119,808槽。逐槽检查准入、输出有效单位及全部有效payload；末尾排空并核对
输入/输出哈希。包括native停顿、下游停顿和非法方向；这些不是整个wafer的地址级trace。

| Width / depth | 组织 | FF/bank | Generic combinational cells/bank |
|---|---|---:|---:|
| 128 / 1 | 独立 | 773 | 1,842 |
| 128 / 1 | FIFO共用 | 516 | 1,584 |
| 128 / 1 | FIFO＋发送器共用 | 515 | 1,452 |
| 160 / 2 | 独立 | 1,291 | 4,549 |
| 160 / 2 | FIFO共用 | 777 | 2,518 |
| 160 / 2 | FIFO＋发送器共用 | 774 | 2,875 |

**B 的发送器共用反而比 FIFO-only 多14.18%的 generic 组合单元。**
这说明模块数减半不保证逻辑变小；当前不能据此推荐统一合并发送器。
这些不同类型通用门的数量不是面积，也没有标准单元库、STA、布线、频率或功耗结果。
Yosys `stat` 的计数与需提供 Liberty 的面积信息是不同输出，见
[官方文档](https://yosyshq.readthedocs.io/projects/yosys/en/0.27/cmd/stat.html)。

最初 `4648b03` 的速率窗口832不整除A的3字周期，触发测试驱动断言；
`3c60583` 按各候选分母分别选窗口后通过。初次运行不是硬件失败，也不混入上述统计。

证据：[模型与探索结果](../../artifacts/results/endpoint/shared_egress_implementation.json.gz)、
[三组织成本表](../../artifacts/results/endpoint/shared_egress_implementation_summary.csv)、
[来源与校验清单](../../artifacts/provenance/shared_egress_implementation_manifest.json)。
历史实验注册见 [SHARED_EGRESS_RTL](../methods/SHARED_EGRESS_RTL.md)，保留原字节哈希；
它不是继续RTL工作的当前任务，当前安排以 [NEXT_TASK](../handoff/NEXT_TASK.md) 为准。
