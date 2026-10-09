# 计算局部性、原生控制器与片上供数：固定完整层结果

2026-10-09。基于 `main@3ce16c1` 继续实现，构建、回归、原生小例子和完整层全部在
hn072 的隔离目录执行。没有更新历史执行源或覆盖历史结果，没有增加 compute、
memory、endpoint、Direct HB 或 prefetch。

**计算并行度匹配后，就近执行仍有收益：307.813 → 258.825 μs，减少 15.915%。**
另一个明确增加有限控制器资源、声明计算 SRAM 供数的对照中，集中与就近分别为
463.263 / 258.830 μs，减少 44.129%。这两个比例回答不同问题；原来的 45.209%
仍是布局、计算并行结构和局部性共同变化的结果，不能当成局部性的隔离测量。

## 1. 匹配四条计算链，单独改变权重与计算的位置关系

保持近分片方案每个 expert 的四条三-block 链、权重内容和物理地址、输入与 FP32
partial/reduce、36 个共享引擎和相同 memory/NoC/SRAM/MC 资源。只将每条 block
链的 compute 在所属 2×2 group 内沿固定顺时针环轮换一步，reduce owner 不动。
例如 `c0 → c1 → c7 → c6 → c0`。每笔权重恰好走一条相邻 C–C link，避免用对角
路径人为惩罚远端对照；所有 expert 的规则预先固定，不根据本批 trace 选择。

旋转与近分片的严格核对包括：忽略 task.tile 后的依赖/读取图相同，全部 128 expert
的 512 个 role 对象内容与地址相同，逐物理引擎的任务数、计算周期及权重字节相同，
张量传输的 source/destination/size 多重集合相同。实际读取集合、逐 memory 字节数
和引擎忙时间也一致。完整 proof 在[注册与分析](../../artifacts/results/system/service_balance/rotation/registration.json)。

| 指标 | 原集中 owner | 四链旋转，远端读权重 | 四链近分片 |
|---|---:|---:|---:|
| 完整层时间 / μs | 472.386 | **307.813** | **258.825** |
| 任务数 | 380 | 411 | 411 |
| 权重字节 | 585,248,256 | 585,248,256 | 585,248,256 |
| 远端权重 payload / B | 438,936,192 | 585,248,256 | 0 |
| C–C 有向 hop-flits | 2,584,780 | 2,607,298 | 34,918 |
| 最忙 SRAM 接收写服务 / μs | 234.966 | 119.700 | 112.788 |
| read row conflicts | 1,037,576 | 571,136 | 572,372 |
| 引擎忙时间合计 / μs | 162.676 | 164.212 | 164.212 |
| 最后 RWDL/HB beat tail / μs | 470.244400 | 304.909680 | 257.022320 |

旋转对照反而略少 row conflicts，却仍慢 48.988 μs。因此此次局部性收益不能用
“近分片恰好行冲突更少”解释。它包含传输路径变化对阻塞、后续请求释放与完成的
反馈，并不是一个固定请求 trace 的纯网络延迟测量。

原集中→旋转同时改变内容布局、依赖结构和消费分布；不能把剩余差值直接称为
“张量并行贡献”。也不能用近分片 hop-flits 的降幅预测同比例加速。沿 intermediate
分片与归约是已有张量并行方法，这里不将其作为新算法贡献。

这一项沿用历史计算吞吐假设和原生二进制，以复用冻结近分片参考，未重跑原三项。
执行源 `492affaa4b72fb2866a26343fcf0c4ae47dc2137`；原三项参考源 `1b086e0`。
其计算侧 SRAM 条件由下面的新服务定义明确化，不能反过来改写历史计算周期。

## 2. 原生服务参考：接口峰值之外还有行切换与刷新

原生小例子直接运行当前 Ramulator bridge：一个 array、read queue=1、最多 8 个
在途 atom，关闭刷新。行命中例子的 128 次回调首尾相隔 127 拍；连续读取 16 行、
每行 64 个 16 B atom，所有相邻行首回调间隔均为 **73 拍**。见
[原生回调、统计与身份](../../artifacts/provenance/service_balance/native-row-reference.json)。

| 参考 | 数据率或时间 | 使用范围 |
|---|---:|---|
| 32×16 B / 3.76 ns 接口峰值 | 136.170 GB/s | 理想持续列数据机会 |
| 64 个 atom / 73 拍，投影至 32 域 | 119.382 GB/s | 无刷新、连续完整跨行的小例子 |
| 最忙 memory 字节 / 接口峰值 | 207.963720 μs | 仅字节工作量必要界 |
| 同字节 / 连续跨行参考率 | 237.208618 μs | 解析参考，非本 workload 精确下界 |

ACT/PRE/refresh 仍是本项目选择的假设，并非公开 SeDRAM 的全套标定参数。
[SeDRAM 原文](https://doi.org/10.3390/electronics12051077) 只作为独立 channel、
128-bit RWDL、3.76 ns 和约 6 ns CASRD 延迟的接口依据。

对旧近分片实际执行，最紧的单 bank/domain 记录为 55,310 次 RD、865 次 row
conflict、61 次 closed-row miss、66 次已服务 REF。当前 read-only、Open、单 bank
与每拍一个命令下，统计条件服务参考为：

```text
RD 命令机会                  55,310 × 3.760 ns = 207.965600 μs
行转换最小附加机会       (865×9 + 61×4)×3.760 ns =  30.189040 μs
已完成刷新冷却（最后一次除外）  65×43×3.760 ns =  10.509200 μs
合计                                              248.663840 μs
258.825000 μs 完成时间高于上述参考                   10.161160 μs
最后 RWDL/HB tail 到完整层完成                        1.802680 μs
```

9 拍来自 RD→PRE 2、PRE→ACT 4、ACT→RD 4，相对连续 RD 的 1 拍机会；closed
miss 计 ACT→RD 的 4 拍。忽略额外 nRAS/nRC、refresh PRE、请求到达空洞与下游等待。
分析逐域检查该参考没有超过实际原生时钟数。计数取决于本次调度与刷新历史，
**它是 trace-conditioned 参考，不是独立于放置/调度的架构下界或可回收 stall**。
上述剩余差距也不能全称为 NoC 开销，或相加重叠的资源等待来解释。

按最新结束的前驱回溯，末端依赖包括 `expert62/tile02` → `expert62/reduce` →
`token1/combine`。它用于定位依赖屏障，并非完整的资源因果关键路径；consumer
分配会影响输入实际交付，不能仅选择最后到达的 DataEdge 就断言它是阻塞原因。

## 3. 独立声明 RWDL、控制器、汇聚与计算 SRAM

`machine/service_profiles.py` 将 interface、array/refresh timing、controller policy、
aggregation、compute service 分开声明。历史默认 profile 保持原行为。新结果给出
`w2w.effective-services.v1` 权威资源记录，C–C 保持实际机器资源，cross-layer 使用
真实 **4096-bit/3760 ps** RWDL/HB，明确排除 SystemSpec 中旧的 routing-only HB
标牌。RWDL 与 HB 仍是同一组 lane，不能重复收费。

刷新相位支持显式 synchronous/staggered 参数；本报告所有完整层仍为同步触发。
交错候选由域号设相位，启动后的首个触发也遵循该相位；不称二者启动历史相同。
没有进行刷新优化扫点。

计算侧声明每 tile **32 个等容量 64 KiB SRAM bank，每 bank 每拍 128 B 计算读**，
合计 4096 B/1 ns，即 4.096 TB/s、32,768 条内部数据位。这里是 **128 BYTE**，
不同于 RWDL 每域 **128 BIT**。保留独立的 activation/状态外部读 256 B/ns 和接收写
256 B/ns，不将外部写口直接冒充计算权重读口。4096 B 的读数据量足以在理想条带化
下为每拍 4096 个 FP8 weight 操作数提供字节；scale 也计入每 tile 的读取量。

新计算规则是 `max(ceil(MAC/4096), ceil(weight_and_scale_bytes/4096)) + ceil(vector_ops/256)`。
每 tile 权重/scale 共 1,573,248 B，按一次完整读取、多个 token 复用；MAC 和读重叠，
向量阶段串行。一个 token 为 max(384,385)+37 = **422 ns**，两个/四个 token 为
841 / 1682 ns。历史一个 token 为 421 ns；新完整层两边同时使用 422 ns。
单元检查将总权重读能力设为 256 B/拍时得到 **6183 ns**，不是只计6146 ns读时间，
也未新增这项完整层实验。

这些 bank/port 是明确的候选服务预算，不是已实现 SRAM macro。宽计算读、外部读
与接收写被视为独立能力；bank 冲突、端口面积、activation/accumulator 内部供数、
scale/dequant 数据通路仍包含在吞吐假设或未标定项中。此 guard 检查总权重供数能力，
不声称 cycle-exact bank simulation 或 4096 MAC/cycle 已经物理闭合。低 compute busy
结论也应附带这一供数条件。

## 4. 一个有限、计资源的 controller 对照，以及必须保留的负结果

每域 native read queue 从 1 项增为 **4 项**，dispatcher 只观察域内最前 **4 个**
descriptor。array active entry=1、refresh priority=1、每域每拍一条命令保持不变。
共享 MC32、返回 staging128 KiB/M、8 atom/域预约（总4096 B/M）、CDC2拍、共享
aggregation256 B/ns、NoC/credit/RX以及 routing 全部固定。

先执行 bounded round-robin：每次只展开有限窗口中的下一 descriptor。这个候选
使行局部性变差，所以不能将它称为“队列更大就更强”的成功基线。保留全部数据后，
增加一个同样有限的 row-batched 策略：优先选择四个可见 descriptor 中，下一 atom
与该域**上次已接纳地址**处于同一行的最早项，否则选择 FIFO head。每域仅一个
row hint；不偷看 native controller 的实际 open row，不扫描全部队列或应用 trace。
原生 FRFCFS 只仲裁已经接纳的四项 atom，仍不是充分优化的通用 controller。

| 原生前端 / 计算供数 | 集中 / μs | 近分片 / μs | 近分片时间减少 | 集中 / 近分片 row conflicts |
|---|---:|---:|---:|---:|
| 历史 q1 + descriptor FIFO / 隐含计算读 | 472.386 | 258.825 | 45.209% | 1,037,576 / 572,372 |
| q4 + 窗口4 round-robin / 显式4096 B读 | **544.581** | **341.507** | 37.290% | 2,551,755 / 1,762,364 |
| q4 + 窗口4 row-batched / 显式4096 B读 | **463.263** | **258.830** | **44.129%** | 822,293 / 571,584 |

后两行具有相同 array、refresh、read queue、数据缓冲、计算供数和物理网络预算；
row-batched 另外明确计行选择状态/比较器，不能声称逻辑成本完全相等。
它避免了 RR 的大量额外行切换，但近分片的明显收益仍然保留。
第一行→后两行也更新了计算供数合同与 bridge，不能将 9.123 μs 的集中改善全部
归因于 queue depth。新 bridge 的默认同步刷新语义保持，native manifest 分别记录。

| 资源压力（row-batched） | 集中 | 近分片 | 含义 |
|---|---:|---:|---|
| 最忙 SRAM 接收写服务 / μs | 234.966 | 112.788 | 实际服务工作，非唯一瓶颈证明 |
| 最忙源 activation/状态读服务 / μs | 3.264 | 1.792 | 独立于计算权重读通路 |
| 引擎忙时间合计 / μs | 163.036 | 164.572 | 近分片额外归约，不是层延迟 |
| 单引擎最大 busy / 完整层 | 3.279% | 2.990% | 以声明的计算供数为条件 |
| 单 source 最大 ready-head credit 等待 / μs | 302.512 | 2.168 | 源注入机会计数，非链路 stall 时间 |
| 有 credit 但队头未供数、后方有 ready / μs | 10.709 | 0.394 | FIFO 策略等待，各指标有重叠 |
| C–C hop-flits | 2,584,780 | 34,918 | 含 header、padding、请求与路径 |
| 预约空间拒绝尝试 | 369,042 | 299,660 | 更大观察窗口改变在途压力，非等待周期 |
| 最后 RWDL/HB tail / μs | 461.085040 | 257.026080 | 请求释放反馈也会改变此时刻 |

不把这些等待、服务与拒绝尝试相加成总 stall。当前结果没有孤立证明必须加宽
NoC、RX 或新 attachment，也没有证明原生 controller 可以忽略。

## 5. 成本账本和仍未闭合的空间实现

| 每 memory 的新增/实际资源 | 数量 | 计费边界 |
|---|---:|---|
| RWDL/HB 实际共享 data lane | 4096 bit / 3760 ps | 32×128-bit；不是两段同速总线 |
| q1→q4 新增 native command entry | 96 项 | 共128项；active/refresh不增加 |
| 每 command entry 裸最小字段 | 24 bit | 20-bit atom地址＋3-bit预约slot＋valid，未含age/control |
| 新增 command 裸最小存储 | 2304 bit = 288 B | 每M；非完整controller面积 |
| RR 选择状态 | 64 bit | 32域×2-bit cursor |
| row-batched 行提示 | 480 bit = 60 B | 32域×(14-bit row＋valid) |
| row-batched 行比较器 | 128×14-bit | 每域四项；仲裁/时序面积未标定 |
| 原生到CDC/汇聚数据预约 | 4096 B | 保持有限，不因q4扩容 |
| 每 compute 内部权重读位宽 | 32,768 bit / 1000 ps | 32 banks×128 B，真实macro成本未知 |

以上是资源代理/服务预算；不能将裸字段换算为真实 PPA。原生 entry 需要追踪返回，
实现可通过共享 descriptor＋有限 atom slot 完成，但完整 bookkeeping 和选择逻辑
必须计入未来实现成本。未为每个域免费复制大队列，也未增加36个引擎以外的算力。

作为中央汇聚的第一项空间成本参考，`machine/rwdl_layout.py` 固定26×33mm field，
32 个 domain digital port 放在均匀8×4网格，各自就地HB落到logic侧、CDC后按
Manhattan路径收集至中心。每域128-bit数据线、沿既有2mm/拍配方估算寄存器：

| 仅数据参考 | 每M | 36M |
|---|---:|---:|
| domain到中心距离之和 | 472 mm | 16,992 mm |
| wire bit·mm | 60,416 | 2,174,976 |
| pipeline bits | 31,744 | 1,142,784 |

后两项约为现有跨reticle C–C data代理的29.9%/30.0%，说明内部汇聚不能长期当作
没有制造成本。网格不是实际阵列floorplan；不含地址/控制/CDC元数据/clocktree，
没有标定controller或array面积。**这份参考没有进入本轮运行时延迟**，不能事后
把wire数加入已有时间，也不声称它已经支持中央汇聚的物理可实现性或成本最优。
[位置与逐域账本](../../artifacts/provenance/service_balance/internal-layout-reference.json)。

## 6. 冻结证据、核验和复现

本轮只新增五项完整层：旋转一项、q4 RR两项、q4 row-batched两项。历史三项只读
复用。所有运行完整排空、36,578,016个16B atom守恒，独立核对任务/读取/传输、
SRAM、MC/outstanding/NI与实际有效资源；新增controller运行的原生1152域实际config确认readq=4、
writeq/refreshq=1、同步刷新、16B payload，未只信任profile标牌。
相关现有回归与新增语义检查通过：旋转匹配合同、计算供数、有限选择状态、刷新
相位、原生73拍小例子；不开展新验收矩阵。定时只读检查随完成退出，日志归档。

| 冻结执行源 | 新执行内容 | 原始目录 |
|---|---|---|
| `492affaa4b72fb2866a26343fcf0c4ae47dc2137` | 旋转 | `rotation-study-v1` |
| `123c4e14493738946cda47fdbc2afc0c915e7d1b` | q4 RR | `service-study-v1` |
| `e41214cd8f2108d2271dbd422deea428f5f2d7a1` | q4 row-batched | `service-row-study-v1` |

服务器根目录 `/Projects/haoning/w2w-full-system-rwdl-20261008`；执行源不更新。
分析源：旋转和RR使用`f147993`，row-batched使用`e41214c`。
BookSim二进制SHA256为`967ef5337da32d6d8be2eb16a20205afeccff212c817964b436256b7b16bb6f7`；
新DRAM bridge SHA256为`e4a09bdd6f60adba53a2505fe5f4172d7af4cff991f84a4df03c725841f5e4bd`，
由`5f88fea`构建，后续C++未改变。旋转保留原DRAM bridge，身份见各分析。
上游Ramulator继续锁定`72427a1bba3771564c4fb0e494ba02242fd1eaa7`。

[归档身份与逐项核验](../../artifacts/provenance/service_balance/archive-index.json) ·
[精简对比](../../artifacts/results/system/service_balance/comparison.json) ·
[旋转分析](../../artifacts/results/system/service_balance/rotation/analysis.json.gz) ·
[RR负结果](../../artifacts/results/system/service_balance/controller_rr/analysis.json.gz) ·
[row-batched分析](../../artifacts/results/system/service_balance/controller_row/analysis.json.gz)。
压缩文件是原输入/摘要/分析的精确gzip，SHA256可核对；原始完整事件、二进制与
环境留服务器。旧报告与旧输入保持原身份。

```sh
# hn072，新分析目录；读取冻结study，不更新执行源
python -m w2w analyze_compute_placement --source <rotation-study-v1> --output <new-analysis.json>
python -m w2w analyze_compute_placement --source <service-row-study-v1> --output <new-analysis.json>
# 新注册、新目录；不能重用旧source identity
python -m w2w run_compute_placement --prepare --output <new-study> \
  --cases gather-stream near-shard-stream --service-profile controller4-row-compute4096
```

目前支持的结论是：在这一个固定RWDL服务点，匹配计算并行结构后局部性仍重要；
明确的有限controller政策与片上供数合同下，近分片的架构优势仍存在。
接收/tag预约仍理想，单中心聚合、内部bank实现与空间收集成本未完成物理标定。
下一步应配平这些实现预算；不再以张量并行本身或更多endpoint机制当作研究贡献。
