# 单 slice 标准单元综合与时序结果

**2026-10-07 最新结果：保留 configurable 核心，source 物理修复与共同 Home RX 特化均完成。**
同 Nangate45 typical 库、2 ns、相同 I/O 合同，布线/提取/修复后 source 面积
21,987.294→15,318.674 μm²（−30.33%）；计入相同的特化 Home RX 和两套 Shared RX，
46,023.320→39,354.700 μm²（−14.49%）。四种模块均通过本轮提取后的 setup/hold、
电气检查和路由器 DRC；最终网表完整字回放通过。
这些是独立小块的局部单元面积与单角时序结果，未测功耗，也未闭合跨 HB 的端到端时序。
完整归因、复现及范围见文末“物理修复与 Home RX 特化”。下面先保留历史映射基线。

## 历史映射基线：5d5a958


2026-10-07，执行源码 `5d5a958`。在 hn072 服务器完成 Verilator / Icarus
RTL 仿真、Yosys/ABC 标准单元映射、OpenSTA，以及映射后零延迟网表回放。
当前可配置 source 保持注册轨迹上的服务，source 映射面积减少 **35.6%**；
计入相同三个 RX 后，局部单元面积合计减少 **16.3%**。
输入 hold 与 RX 最大电容仍有违例，因此这是修复前的综合面积结果，尚未时序收敛，
没有 post-layout 或功耗结果。

## 固定比较与计费边界

- 原生完整字 256 bit，Home 256/D1、Shared 160/D2。
- Duplicated：Home、Left、Right 各自配置 TX FIFO/gearbox。
- Configurable：Home TX，加一套 Shared TX，在第一次 HB 之前静态选择方向。
- 相同 native trace、目的地、下游背压、输出位宽和三个 RX。
  每个架构计入一套 Home RX 和两套 Shared RX，即使某次静态配置只使用一个共享方向。
- 分别综合 source 与 RX；配置输入不绑常数，不通过删除备用物理方向节省硬件。
- 同一 Nangate45 typical 库（1.1 V、25°C）、2 ns 时钟、0.05 ns uncertainty、
  最大 I/O delay 0.2 ns、最小 I/O delay 0、BUF_X1 输入驱动与 5 fF 输出负载。
  两者使用同一综合选项；ABC 目标为 2,000 ps。

这是公共 logic 标准单元库下的相对比较。Source 必须处于第一次 HB 之前，
当前库并不证明该逻辑已经在 DRAM 工艺或某个实际 WoW 堆叠上实现。
HB、驱动/长线的真实电气参数、封装、DRAM array/controller 均不在本轮计费内。
物理数据 lane 仍为 256+160+160=576 bit；不能据此声称长线或 HB 减少。

## 功能与映射验证

三个后端分别完成相同的 14 条成对轨迹：Verilator RTL、Icarus RTL、
Verilator 映射后零延迟网表。每个后端共 181,308 个成对周期，
每个架构接收并在正确目的地逐 bit 恢复 **124,834 个完整字**。
RTL 两个 simulator 的周期与计数完全一致；映射后回放的外部计数与周期也一致。
覆盖 Home、Shared、8:5 混合、稀疏/突发源、间歇背压、长停顿与有限尾部，两个方向均测。

保留 native/HB/RX 停顿稳定性、逐字 payload/tag/destination、无丢失/重复、
以及配对架构逐周期输出检查。RTL 另检查内部占用与位守恒；映射后不读取已消失的
内部信号，只保留外部 scoreboard。变更静态方向与破坏 payload 的两个负测试均触发
预期 checker。所有映射使用的 cell 都有同库生成的功能模型。
这不是形式证明、SDF 仿真或物理链路验证。

Verilator 未报告 latch、多驱动、未驱动或组合环；位宽、命名、未使用信号警告
保留在原始 lint 日志中。此次同时修正了一个验证缺口：D1 的单 bit FIFO count
原本无法用 `count > 1` 检出溢出，现改为截断前检查 next occupancy。
共同 TX 的输出使能从 `units != 0` 简化为 `words != 0`，并加等价 invariant；
没有增加存储或流水延迟。上述仿真和网表结果覆盖修改后的实现。

## 映射面积

单位 μm²，来自同一 Liberty 的标准单元面积总和，尚未进行 hold/capacitance 修复。
不包括 placement 空白、CTS、布线或物理优化；分块合计不等于完整布局后的 core area。

| 模块 | 全部单元面积 | 时序单元面积 | FF 数 |
|---|---:|---:|---:|
| Duplicated source | 17,265.528 | 8,496.838 | 1,879 |
| Configurable source | 11,123.854 | 5,412.834 | 1,197 |
| Home RX，每套 | 6,186.894 | 1,175.720 | 260 |
| Shared RX，每套 | 7,155.134 | 1,754.536 | 388 |
| Duplicated source + 3 RX | **37,762.690** | — | **2,915** |
| Configurable source + 3 RX | **31,621.016** | — | **2,233** |

三个 RX 的共同成本为 20,497.162 μm²。因此 source 的 35.6% 节省在完整局部计费后
成为 16.3%。这支持利用静态方向互斥减少 source 硬件；同时说明 RX/reassembly
是重要成本，不能把只看 TX 的比例直接当成 endpoint 总收益。
当前通用 RX 也未被证明是最优实现。

## 2 ns 下的 STA

所有值均为 ns；setup/hold 正值表示该报告路径有裕量。理想时钟、无提取线 RC。
`check_setup` 无缺失时钟/I/O 约束等检查问题；这不等于时序已收敛。

| 模块 | 全部路径最差 setup slack | 全部路径最差 hold slack | 寄存器间 setup slack | 寄存器间 hold slack |
|---|---:|---:|---:|---:|
| Duplicated source | +1.01 | **−0.02** | +1.15 | +0.06 |
| Configurable source | +1.06 | **−0.03** | +1.20 | +0.06 |
| Home RX | +0.89 | +0.01 | +0.90 | +0.07 |
| Shared RX | +1.09 | **−0.01** | +1.13 | +0.06 |

负 hold 来自零最小输入延迟下的输入路径；没有通过修改该约束把违例隐藏。
Home RX 另有 4 个最大电容违例，Shared RX 每套有 1 个，最差分别为
−4.42 fF 与 −4.49 fF。Source 未报告相应电气违例。
原始路径与 pin 记录在证据包和 JSON 中。

所以本轮可以报告 **setup 有裕量，但输入 hold 与 RX 电气约束尚未闭合**。
修复会改变面积和路径；当前数字不是最终 signoff 成本，不将 2 ns 目标或
这些 pre-layout slack 换算成已实现 Fmax。未运行功耗分析，也没有功耗节省结论。

## 复现与归档

服务器运行目录：
`/Projects/haoning/w2w-memory-slice-20261007/asic_5d5a958`。
完成时间 `2026-10-07T13:10:36Z`，退出码 0，日志包含 `ASIC_PIPELINE_COMPLETE`。
流程完成与时序收敛是两个独立状态；结果 JSON 明确记录 `timing_closed=false`。

工具：Verilator 5.052（conda-forge）、Icarus 11.0、Yosys 0.69+
（`9f09efcdb-dirty`，conda-forge 构建的实际版本字符串）、OpenSTA 3.1.0
（`b7d866ff69e618c025510423ffb65a202796b4f9`）。
工具在实验目录下隔离安装，未修改系统或 Vivado 安装。
当前 PATH/配置环境未发现 VCS/DC/Genus/PrimeTime；不据此推断学校没有许可证。

```sh
source /Projects/haoning/w2w-memory-slice-20261007/asic_tools/env.sh
cd /Projects/haoning/w2w-memory-slice-20261007/source_5d5a958
python3 w2w/experiments/run_endpoint_asic.py \
  --traces /Projects/haoning/w2w-memory-slice-20261007/inputs \
  --liberty /Projects/haoning/w2w-memory-slice-20261007/asic_tools/lib/NangateOpenCellLibrary_typical.lib \
  --output /Projects/haoning/w2w-memory-slice-20261007/asic_replay_new --period 2
```

重新执行时使用新 output 目录。输入 trace 哈希由 runner 对照历史 roundtrip artifact
检查。库来源、库 SHA、完整约束和方法见
[方法文件](../methods/ENDPOINT_ASIC_SLICE.md)。

- [结果 JSON](../../artifacts/results/endpoint/endpoint_asic_slice.json.gz)：原始运行 manifest、逐轨迹计数、面积/时序汇总与未解决项。
- [证据包](../../artifacts/provenance/endpoint_asic_slice_evidence.tar.gz)：仿真/lint/STA/综合日志、映射网表与 cell model、脚本、工具环境锁定及安装记录。
- [归档清单](../../artifacts/provenance/endpoint_asic_slice_manifest.json)：文件 SHA 与排除项。
- [执行入口](../../w2w/experiments/run_endpoint_asic.py) 与 [STA 约束](../../rtl/asic/slice_sta.tcl)。

Vivado 作为补充证据保留；早期 FPGA 输入约束错误及被中止的重跑见
[Vivado 诊断报告](ENDPOINT_VIVADO_SLICE_REPORT.md)，不与这次 ASIC 结果混用。
本轮停在同库、同约束的单 slice 比较，不扩展 placement、32-bank 聚合或整片 P&R。

## 补充：零线 RC 的网表修复诊断

源码 `61ba73f`，2026-10-07T13:37:32Z 完成。RTL 与边界约束均未改变；
修复只在映射网表上加 BUF_X1、将过载 NOR4_X1 替换为 NOR4_X2。
数据路径未设 false path，最小输入延迟仍为 0。修复前所有负 hold 都位于
input→register；寄存器间 hold 已为正。

| 模块 | 新增 hold buffers | 驱动强度调整 | 修复后面积 μm² | 最差 setup ns | 最差 hold ns |
|---|---:|---:|---:|---:|---:|
| Duplicated source | 258 | 0 | 17,471.412 | +0.990369 | +0.000888 |
| Configurable source | 513 | 0 | 11,533.228 | +1.062070 | +0.004900 |
| Home RX | 0 | 4 | 6,191.150 | +0.892862 | +0.005703 |
| Shared RX，每套 | 3 | 1 | 7,158.592 | +1.091455 | +0.000094 |

该零线 RC 模型中的 setup、hold、电容/转换时间检查均通过。
Configurable 付出了更多缓冲，source 绝对面积差从 6,141.674 降为 **5,938.184 μm²**，
相对节省为 **34.0%**；计入相同三个 RX 后为 **37,979.746→32,041.562 μm²，−15.6%**。
全部 14 条成对 mapped trace 再次通过，字数与周期均与 RTL 一致。

这只回答修复成本的逻辑级诊断问题，**不是 physical hold repair 或 post-route 时序收敛**。
没有 CTS/skew/提取 RC；其中很小的正 hold 裕量也不能外推到其他角或物理实现。
随后按用户要求注册 OpenROAD 对照，从未加这些 ECO 的原始网表出发，独立报告工具自动
修复后的结果。统一 ingress register 也不会消除输入口到该寄存器本身的 hold 要求。

[修复结果](../../artifacts/results/endpoint/endpoint_asic_repair.json.gz)、
[原始日志与网表](../../artifacts/provenance/endpoint_asic_repair_evidence.tar.gz)、
[哈希清单](../../artifacts/provenance/endpoint_asic_repair_manifest.json)。


## 物理修复与 Home RX 特化（2026-10-07）

### 改动与控制

本轮保留原 source RTL：一套 Home TX、一套 Shared TX，第一次 HB 之前静态选方向。
没有增加 dual-leaf、ingress pipeline 或动态共享方向；Shared 160/D2、布局和输入轨迹不变。
唯一数据通路改动是 Home RX：在 WIDTH=256、有效 beat_units=8 的既有合同下，
用 256-bit payload 和 full 标志替代通用 reservoir/count。支持同拍 pop/push，
背压时保持有效字，不添加 bypass。原通用分支保留为对照；两种架构使用同一特化 RX。

物理实现仍用原 Nangate45 typical Liberty（1.1 V、25°C），SDC 的 2 ns、
0.05 ns uncertainty、I/O max=0.2 ns/min=0、BUF_X1 drive、5 fF load 全部保持相同。
OpenROAD v2.0-17598-ga008522d8，ORFS 平台与库均来自
`9b26ff8ff651fc0b696f7ef20a356865ca6068bb`。
每块初始 utilization=30%、placement density=40%、方形 core、5 μm margin、seed=42。
分别完成 placement、CTS、自动修复、详细布线、OpenRCX、显式 read_spef、propagated-clock STA。

修复策略对所有块相同：hold margin=0.05 ns，每阶段最多三次自动修复；
遇到单次 buffer 数上限时保留已插单元、合法化并更新 RC，再继续。
还保留从 50% 到工具允许最大 100% 的有限重启选项；最终采用的块没有使用该重启。
若提取后仍有电气违例，则从原映射网表重跑一次，repair_design cap_margin=20%。
Shared RX 与原通用 Home RX 用到此电气重试，已闭合的 source/特化 Home RX 不受影响。
这是修复器的余量/工作量设置，不是放松输入延迟或输出负载。

试跑的 0.02 ns hold margin 在显式载入 SPEF 后仍有负 slack，因此未作为正式结果。
同样，初次 Shared RX 的两个电容违例及通用 Home RX 的一个违例保留为失败记录，
未混进最终闭合比较。三个恒零 Home units 输出经映射结构验证后，仅过滤旧版
check_setup 的恒定端点提示，没有新增数据 false path。提取检查逐一确认未标注 driver
都没有其他连接负载；没有带负载的 net 缺失 RC。

### Source：额外 hold buffer 没有抵消方向复用收益

面积单位 μm²。这里计功能、时钟及修复单元，单列 tap，不含 placement 留白。

| 指标 | Duplicated | Configurable |
|---|---:|---:|
| 原映射面积 | 17,265.528 | 11,123.854 |
| 最终 hold buffer 数 | 2,669 | 3,026 |
| hold buffer 面积 | 2,135.182 | 2,414.748 |
| CTS buffer / dummy load 数 | 336 / 254 | 199 / 171 |
| CTS buffer + dummy load 面积 | 636.804 | 397.404 |
| **提取后修复面积** | **21,987.294** | **15,318.674** |
| 相对原映射的净增量 | 4,721.766 | 4,194.820 |
| FF 数 | 1,879 | 1,197 |
| 另计 tap 面积 | 113.316 | 91.238 |

Configurable 多 357 个 hold buffer，但总物理增量更小。
方向复用的绝对节省为 **6,668.620 μm²**（−30.329%），
FF 差仍为 682，保持“一套 Shared TX 状态被删除”的结构解释。
净增量包含 clock、插入、删除、尺寸调整，不能只从 hold buffer 数或最差 slack 推断。
表中 clock/hold 分类来自最终实例名与 master 清单；其他电气修复/重构保留在完整
初始/最终网表、逐实例清单和阶段总面积中，不把所有剩余增量冒充为纯 hold 成本。

Source 路径分类，单位 ns：

| 路径类型 | Dup setup | Dup hold | Cfg setup | Cfg hold |
| 输入→寄存器 | +1.050922 | +0.023190 | +1.002006 | +0.035715 |
| 寄存器→寄存器 | +1.068283 | +0.060025 | +0.998935 | +0.059970 |
| 寄存器→输出 | +1.296427 | +0.286969 | +1.310715 | +0.262357 |
| 输入→输出 | +1.254268 | +0.123004 | +1.278878 | +0.155760 |

最差 hold 仍属于输入→寄存器；寄存器间 hold 均为正。没有证据要求为这些输入路径
改成 shared-core＋dual-leaf。所有精确 startpoint/endpoint 见 JSON 的 audit.paths。

### Home RX：共同实现优化，单独归因

| 指标 | 原通用 Home RX | 完整字 Home RX |
|---|---:|---:|
| 原映射面积 | 6,186.894 | 1,961.750 |
| 提取后修复面积 | 9,890.944 | 3,815.770 |
| hold buffer 数 | 1,115 | 2,023 |
| hold buffer 面积 | 897.750 | 1,614.354 |
| 最终 setup slack | +0.831098 | +1.361952 |
| 最终 hold slack | +0.040300 | +0.045307 |

修复后的共同节省为 **6,075.174 μm² / Home RX（−61.422%）**。
特化 RX 组合路径更简单，却需要更多输入 hold 修复；这部分成本全部计入。
这是既有完整字合同下的实现特化，两种架构同时受益，不算作方向复用新增贡献。
原通用 Home RX 对照也完成同策略修复、提取和最终网表回放。

共同 Shared RX 未改 RTL：原映射 7,155.134、物理修复后 10,110.128 μm²/套；
1,267 个 hold buffer，面积 1,245.678 μm²。最终 setup=+0.981954 ns、
hold=+0.026565 ns。全四种正式块及通用 Home 对照的电气违例、路由器 DRC 均为 0。

### 合计时保持相同分母

| 独立块单元面积合计 | Duplicated | Configurable | 方向复用节省 |
|---|---:|---:|---:|
| Source + 原通用 Home RX + 2 Shared RX | 52,098.494 | 45,429.874 | 12.800% |
| **Source + 特化 Home RX + 2 Shared RX** | **46,023.320** | **39,354.700** | **14.490%** |

两行的 source 绝对差均为 6,668.620 μm²。Home RX 共同优化只改变分母，不能把
其 6,075.174 μm² 再加进方向复用的绝对收益。若计入所有 tap，第二行变为
46,312.196→39,621.498 μm²（−14.447%）；结论一致。

上述合计不是整片 wafer 面积，也不是一块联合布局后的 core 面积。
三个 RX 对应此局部 star 的三个潜在直接目的地；不能把这份计费方式自动乘到
所有 compute 而重复计费。实际 HB、wafer 长线、驱动、供电网络不在这些单元面积里。

### 功能、完整性与复现

- Home 独立对照：100,004 周期，包含长停顿、同拍替换和中途复位。
  62,887 次接受、62,886 次交付、1 字按复位合同丢弃；复位丢弃单独计数，
  不把它当数据丢失。所有有效 payload、ready/valid 和 pending bits 与通用分支一致。
- 正式 14 条成对轨迹：Verilator RTL、Icarus RTL、最终物理网表零延迟回放全部通过。
  每架构、每后端 124,834 字，181,308 成对周期；完整 payload/tag/目的地一致，
  背压和停顿稳定性检查通过，两个故意破坏的负测试触发预期 checker。
- 原通用 Home RX 的最终物理网表另外回放同 14 条轨迹，外部计数/周期与特化版一致。
- 316 份归档文件 SHA 全部核对；RTL、SDC、库、复用 manifest 哈希链及网表哈希一致。
  物理数据库逐实例面积与最终 Liberty 单元面积交叉核对，误差 <1e-5 μm²。

执行来源分开记录：source 闭合于 `9cae62d`，特化 Home RX 闭合于 `5c7fcc0`，
最终 Shared RX、电气重试及整套回放为 `6ecba5c`，正式流程完成于
2026-10-07T14:48:04Z。闭合块在相同 RTL/SDC/库/工具下复用，保留其原始日志和哈希；
没有把缓存结果伪装成重新运行。完整从头复现可不使用 --reuse-closed。

服务器主结果：`/Projects/haoning/w2w-memory-slice-20261007/physical_6ecba5c`；
通用 Home 对照：`physical_home_generic_6ecba5c`、`generic_home_replay_6ecba5c`。

- [物理结果 JSON](../../artifacts/results/endpoint/endpoint_physical_slice.json.gz)
- [物理数据库、SPEF、网表、原始日志、完整输入与脚本](../../artifacts/provenance/endpoint_physical_slice_evidence.tar.gz)
- [316 文件归档清单与 SHA](../../artifacts/provenance/endpoint_physical_slice_manifest.json)

这里的“通过”限定于同一 typical corner、2 ns 和注册 I/O 条件。
没有 MCMM、SDF 动态仿真、formal equivalence、功耗或 HB/wafer 长线模型；
相加的独立块不能证明跨 HB 的端到端物理时序。2 ns RTL 时钟也不直接校准机制模型的
TB/s。局部结果支持保留静态 Shared TX 复用，当前不扩 dual-leaf、Shared RX 优化或
32-bank RTL；下一步回到系统服务与完整路径成本的归因。
