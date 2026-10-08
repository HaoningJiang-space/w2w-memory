# DRAM 命令后端闭环验证结果

公开 HBM2 命令模型已接入有限请求、endpoint、HB 与 RX 的闭环。8 次完整对象回放全部通过；原生后端根据 ACT/PRE/RD、刷新和控制器队列决定完成时间，未将 DRAM 简化成事后添加的固定延迟。默认 slot 模型仍保持原语义。

这是 **公开 DRAM 参考组织下的接口与执行验证**。HBM2 profile 的共享通道预算与旧模型不同，且部分时序是上游估算；尚不能作为定制 WoW DRAM 的绝对性能或工艺 signoff。

## 实验身份与输入

- 执行源码：`5d20b500c6439617c1dab11366955d69e88b8006`；服务器 `hn072@143.89.78.72`，CPU 执行，无 GPU。
- Ramulator：`72427a1bba3771564c4fb0e494ba02242fd1eaa7`；HBM2_2Gb / HBM2_2000Mbps，36 channels、每 channel 32 banks。
- 输入：已归档 `h0_b1` 中第一个完整读任务，`batch0/layer0/expert18`，owner compute 8。
- 对象读取：18,878,976 bytes，589,968 个 32-byte 字，未缩小权重；128 个 resident objects 全部保留。
- 隔离：该任务依赖/起始时间归零，只执行这一项；不是完整 decode batch 或整个 MoE 推理。
- 预算：N=192，source/HB/RX 继承冻结候选；request/link 各 1 slot；native 固定延迟为 0。

参数、边界和复跑命令见[方法](../methods/DRAM_COMMAND_BRIDGE.md)。所有解析时序、地址组织和哈希在[原始归档](../../artifacts/results/dram/command_bridge/manifest.json)。

## 同一冻结对象的回放

单位为 µs。两列的 native 资源预算不同，不能把列间比值当成同硬件优化的 speedup。

| 冻结设计 | 旧 slot 参考 | HBM2 命令参考 |
|---|---:|---:|
| Home | 18.881536 | 642.437120 |
| k2 reciprocal | 9.442304 | 321.333248 |
| wide k3 pair | 9.442304 | 321.164288 |
| B configurable | 12.104704 | 395.289600 |

每项新旧对照拥有相同 residency hash 和逐 bank 字节数。原生控制器分别接受和服务 589,968 次读，无写入、无 write-forwarding；结束时原生和适配器 pending 都为 0。B 的控制器拒绝了 3,782 次尝试，重试后所有字节仍恰好交付一次。每 slot 都检查 outstanding、source、RX、字节/bit 守恒。

在这一个孤立任务中，Home 的所有字节由一条 HBM2 channel 服务；k2 分到三条 channel，其中 home 占约一半；wide k3 分到两条 channel且约等分。k2 和 wide 因而接近相同完成时间。B 的 home channel 承载 363,056/589,968 个字，份额更高，结束更晚。这是原生供给与固定驻留共同决定瓶颈的实例，不能外推为 k2 在真实多任务流中普遍等价于 wide。

旧模型中 1 TB/s 的单 memory 供给在这里被公开 HBM2 通道约束替代，Home 的有效服务约 29.4 GB/s。**这个巨大绝对差异来自参考组织变化，不是发现了定制 WoW DRAM 必然慢三十多倍。** 新后端的用途是揭示哪些结论依赖原生服务假设，并为后续标定提供可替换接口。

## 正确性证据

服务器完整 Python suite：193/193，通过，包含 8 项 DRAM 相关检查。原生检查未跳过，覆盖行命中/冲突、同 bank 与跨 bank 请求、刷新命令、有限控制器队列和 HB/RX 反压。

8 次回放共交付 4,719,744 个 32-byte 字，其中 2,359,872 个经过原生命令模型。服务器与本地分别重新读取归档，检查文件哈希、完整对象、冻结 route/bank 字节和任务完成。加强后的本地审计还逐 channel 对照原生控制器的接收/服务计数及实际推进周期。这些是独立的账本复算，**不等于第二套独立 DRAM 电路时序模型**。

[构建和测试证据](../../artifacts/provenance/dram_bridge/build_receipt.json)记录 GCC、CMake、动态链接库路径和 SHA256；[归档审计](../../artifacts/provenance/dram_bridge/archive_readback.json)记录逐字核对。上游构建自动生成的 DRAM C++ 差异随归档保存，并附上 MIT license；没有把生成差异称作手工微架构修改。

## 尚需做什么

1. 固定同一 DRAM 组织后，扩展到完整冻结 batch、不同 outstanding 和队列深度，评估并发需求；当前只是一个完整对象探针。
2. 保持唯一静态地址映射，比较公开支持的 row policy / address mapping；不能按活动窗口免费重映射。
3. 用实际 WoW 导出路径的宽度、原生周期和共享资源替换参考 HBM channel。需要可追溯的数据手册、测量或指定宏模型，不能通过缩短 tCK 凑回 1 TB/s。
4. 物理证据仍是局部 Nangate45 slice；DRAM 宏、HB/RDL 寄生、顶层多角时序、DRC/LVS、IR/EM 等全片资产尚未提供。DRAM 时序闭环与整片 signoff 是两项不同的交付。

代码按 service/dram、experiments、validation 分层；没有新增根目录研究脚本，也没有改写旧实验结果。
