# 单 slice 标准单元综合与时序结果

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
