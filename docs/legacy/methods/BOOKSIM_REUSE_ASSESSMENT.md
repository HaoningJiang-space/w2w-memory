# 复用 wafer_simulator 的已优化 BookSim

2026-10-09。本次检查本地与 eex005 的 `wafer_simulator`，并在服务器执行原生接口测试。
**后续系统主网络优先复用其在线 C++ 后端；本项目新写的 Python 网络只保留为小系统合同参考。**
官方 stock BookSim2 保留独立参考，已有上游 fork 和历史结果均不覆盖。

## 找到的实现与证据

仓库 `https://github.com/HaoningJiang-space/wafer_simulator.git`。
审查期间从 `56e9371` 前进到 `0c56c24b4bf602b8b2c036681f526971305dde99`；两者之间
只改独立 machine 审计和相应 fixture，下面的 native、wrapper 与所测两份测试未变。
原始作者树为 `9470042fb2d8b5368556e46cc75ac818dbf31522`，以普通文件保存在该仓库。

| 组件 | 用途 |
|---|---|
| `patches/booksim-wafer.patch` | 合并完成语义修复和优化：拓扑 const reference、密集状态、CSR 依赖、减少无效 Evaluate |
| `adapters/native/online_booksim.cpp` | 持久 native 进程，submit/advance、逐 flit 记录、到事件边界返回、完整排空 |
| `adapters/online_booksim.py` | Python IPC、身份与完成检查 |
| `patches/booksim-endpoint-hooks.patch` | 数据供给与接收端 credit hook |
| `adapters/native/endpoint_manager.hpp`、`boundary_booksim.py` | supply/commit；未供数据不得注入，未提交接收数据不返还 credit |

其中 `adapters` 相对 `src/wafer_sim/`。补丁应作用于隔离的 pinned 构建树，不能覆盖作者快照。
目前 `build/booksim-online/online_booksim` 与 `build/booksim-boundary/endpoint_booksim` 均已存在。
二进制原构建分别记录 `582ded5` 和 `bec1051`；它们不是本次重新编译的二进制。

此前完整回放的 `implementation_equivalence.json` 保存 corrected-reference 002 与 CSR 006
的完整事件一致性，观测墙钟比分别 4.6504 / 3.4462。原报告说明运行重叠且 reference 曾被 debugger
采样，故这些是历史观察值，不是本轮独立计时，也不是相对 stock BookSim 的普遍加速比。
另一个 3.09×/4.21× 结果来自 Python 任务准入扫描优化，不能算成 BookSim 内核加速或相乘。

## 本次实际验证

在 eex005 的独立输出目录运行原项目的 `test_online_booksim` 和 `test_memory_boundary`：
**14 项通过，2.106 s，无 skip**。覆盖在线/离线时间戳对照、共享链路、credit 反压、
未供数据不发送、延迟接收提交、空闲推进、完整排空以及接收后写入/任务生命周期。
源、二进制及组件哈希、日志保存在本仓库 `artifacts/provenance/booksim_reuse/`。
这是现有组件再验收；没有重新运行完整大 trace，没有修改另一个项目。

## 接入必须保持的合同

1. **包化不同。** 该 trace fork 将一个 message 展开为若干单 flit packet；
   当前 Python 参考网络是多 flit packet、尾 flit 释放输出 VC。二者不能直接声称逐周期等价。
   必须统一有效载荷、头部、padding 与 flit 宽度后比较。
2. **当前在线模式是一 class、一 subnet；bounded 模式进一步要求一 VC/private buffer。**
   不能把三类流量的标签当作已有的三个隔离 virtual network，也不能复制物理带宽。
   新请求/响应协议需要检查缓冲依赖；多 VC 支持若必要，单独修改接口和验收。
3. **submit 不是有限 NI 的 try_send。** native 接口可登记消息；它不自动限制外部待注入消息数。
   有限 NI/DMA 额度必须在系统适配层预留，拒绝时不登记事务，注入完成后才释放源状态。
4. **network complete 不等于 SRAM commit。** bounded hook 可扣留接收 credit，但任务解锁仍须等
   有限本地写入完成；不能使用基础 OnlineBookSim 的整消息完成直接绕过 RX/SRAM。
5. **ps 与 native cycle 单向映射。** kernel 决定允许推进的边界；native `advance` 可提前在事件处返回。
   不得跳过尚待处理的 native 事件，空消息表也不代表 credit 已排空。
6. 原作者 routing 支持不规则图，不等于自动获得任何新协议的无死锁证明。
   首先采用明确的 mesh/路由/VC 合同，验证新的请求、响应与激活竞争。

## 对当前重构的调整

- `19a10b1` 的 Python prototype 已通过 25 项测试，1 项 native 可选测试跳过。
  它适合检查缺路拒绝、字节与 credit 守恒、共享容量、整数时钟和 task 生命周期；不继续扩成主 NoC。
- 先沿用已优化 BookSim 和 bounded endpoint 接口，接同一个 2×2 C＋4M 的 B1 事务 fixture。
  先闭合注入额度、包化、接收提交和时钟，再做 matched 网络对照。
- Ramulator 使用现有 pinned bridge；`RamulatorAbsolute` 的 ps 适配不能因接口存在就记为 native 已通过。
- 原项目还新增了 `architecture/wafer_machine.py`、`adapters/wafer_machine.py` 和
  `docs/WAFER_MACHINE.md`：已经有显式 stitching、HB、MC、SRAM、请求/响应的系统组织。
  这些应逐项复用或作为对照；其 memory 是解析 bank/channel，不能与 Ramulator 的同一服务重复收费。
  本次只核查该结构，没有冒称其新增 machine campaign 已完成。

这一选择复用的是已验证的网络和交互接口。B0/B1/B2 的物理资源、对象驻留、原生 DRAM 与
新工作负载合同仍由本项目显式定义，不把另一个项目的固定本地时间或硬件速率直接移植。
