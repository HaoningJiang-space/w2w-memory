# 当前进展：单 slice 标准单元比较已完成

研究主线：用较少共享接口硬件，使邻近 compute 利用已有闲置 DRAM 服务。
方向选择固定在 source 侧、第一次 HB 之前；每条 M→C 必须是合法 overlap 边。
不引入 logic 侧 C→C 转发，不实现 DRAM array/controller 或整个 wafer。

## 最新证据

[ASIC 报告](../reports/ENDPOINT_ASIC_SLICE_REPORT.md)，执行源码 `5d5a958`，
在 hn072 的隔离目录完成 Verilator/Icarus、Yosys/ABC、OpenSTA 与映射后零延迟回放。
Home256/D1、Shared160/D2、同 Nangate45 typical 库、2 ns 约束。

每个后端 14 条成对轨迹通过，每架构 124,834 个完整字逐 bit 恢复，
181,308 个成对周期；两种 RTL simulator 与映射后外部周期/计数一致。
两个注入错误均触发预期 checker。

Source 单元面积 17,265.528→11,123.854 μm²（−35.6%）；
计入同样一套 Home RX + 两套 Shared RX，合计 37,762.690→31,621.016 μm²（−16.3%）。
Lane 不变。所有 setup slack 为正，但输入 hold 和 RX 最大电容有违例；
尚未时序收敛，未做 P&R 或功耗。面积是修复前映射结果。

此前 [roundtrip 报告](../reports/ENDPOINT_ROUNDTRIP_REPORT.md) 保留更宽目录的历史
26 条轨迹，包括 192/D1=.5、192/D2=.75。不要把历史计数混入本轮 14 条 ASIC 轨迹。
[Vivado 报告](../reports/ENDPOINT_VIVADO_SLICE_REPORT.md) 记录旧输入约束错误，
修正后的 FPGA 重跑为优先 ASIC 而中止；没有修正后的 FPGA PPA 结论。

## 下一步围绕研究判断

当前结果支持：静态互斥共享方向能够减少 source 硬件；加入 RX 后收益仍在，
但总收益小于 TX-only 比例。不要再以 FIFO bits 直接推断完整 endpoint 面积。

如继续推进硬件证据，先在相同库和边界约束下修复已知 hold/cap 违例，
重新核对功能和面积变化，再判断是否值得进入局部物理实现/功耗。
不把部署更多 EDA 工具本身当研究进展，不自动启动新 sweep 或工程重构。
Source 位于第一次 HB 之前，Nangate45 仅验证 logic 库相对成本；其具体工艺/层归属
仍需在最终架构中说明。

## 保持范围

private、k2、full-width direct 保留为系统层基线；当前不扩 wafer LP、
matching/cycle、任意 k、深 FIFO scheduler、BO/Benders、placement 或真实 trace。
32-bank 聚合、真实 HB 延迟和 metadata 汇聚留待单 slice 判断之后。
不把本轮三个 RX 的计费范围直接套入每-M 成本账本，以免重复计费。

当前实验服务器为 `hn072@143.89.78.72`，根目录
`/Projects/haoning/w2w-memory-slice-20261007`；工具环境在 `asic_tools/env.sh`，
结果在 `asic_5d5a958`。源码、工具环境、库与输入 SHA、报告均已归档。
