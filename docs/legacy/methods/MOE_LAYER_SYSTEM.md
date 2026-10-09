# 一个真实 routing 驱动的完整 routed FFN 层

当前源码执行主干仍是 `SystemExecution`。网络适配器复用
`wafer_simulator@0c56c24b4bf602b8b2c036681f526971305dde99` 的持久 native
BookSim、supply 和 receive/commit 协议；未重写 router/credit 内核。
本轮实验在 hn072，保留独立目录与逐次退出状态。

## 固定任务与机器

输入来自既有 `cohort_replay/inputs` 的逐 request routing，选择 `c0_b1`、layer 0、
第 17 个 decode step（1-based）。沿用训练阶段冻结的 marginal LPT expert owner；
不重新采集 routing，不按三种运行的结果修改 owner。输入包含一 token、八个专家。

采用[官方模型配置](https://huggingface.co/Qwen/Qwen3-235B-A22B-FP8/raw/main/config.json)
对应的既有登记：hidden=4096、expert intermediate=1536、128 experts、top-8。
每专家 gate/up/down 的 FP8 参数与每 128×128 block 的 FP32 scale，共 18,878,976 B。
本轮共读 151,031,808 B。模型配置身份沿用旧 spec 中的 SHA-256。

每个 128-wide intermediate tile 读取三矩阵对应权重、执行 up/gate、SiLU/product、
down 部分和；下一个 tile 接收 BF16 输入及 FP32 running sum。一个 cohort 内同专家
的 token 共用权重 tile，跨 cohort 不缓存。本轮是显式 blocking tile 调度，无额外预取。
末尾输出按真实 token 归属返回并完成 weighted combine；任务图共 98 个节点。
起点是已在 SRAM 的输入激活，终点是 combine 完成、输出交给层外消费者。
不包含 routing projection、attention、KV 或数值推理验证。

全部 128 个专家均冻结驻留：每个 tile 的一半在 owner 的 home memory，另一半在
固定相邻 `owner XOR 1` 的 memory，不复制字节、不迁移。采用 64 KiB 段交错发起
home/peer 读取。各运行的任务图、owner、物理地址和算术工作完全相同。

| 项目 | 登记值 |
|---|---|
| 规模 | 6×6 compute mesh；36 reticles、每 reticle 1 聚合 tile/engine/MC；36 memories |
| C–C | 显式 stitching 假设；每方向 256 B/ns，3-cycle router，2-cycle/10 mm link |
| 宽 NoC | C–C 512 B/ns；router/NI 的缓冲字节预算固定，flit 数相应减半 |
| Home HB | 256 B/ns，1 cycle，20 μm；宽 NoC 不加宽 HB |
| SRAM | 每 tile 2 MiB；DMA 写端口 256 B/ns，activation/最终 read response 竞争 |
| 计算 | 每 tile 4096 MAC/cycle、256 vector ops/cycle，1 ns；未硬件标定 |
| 请求前端 | 4 个 4 KiB descriptor/tile/cycle；32 个 outstanding/tile |
| MC | 32 个 descriptor slots/M；返回空间随 slot 预留 |
| NI | TX 64 KiB；每流量标签最多 16 个接收 packet 预留，3 类共 197,376 B |
| DRAM 地址 | 32-byte native word，连续地址按 32 banks 交错；每 M 512 MiB |

NIC 接收预留在 packet admission 时完成；有限的独立 request/response/activation
接收存储解除一 VC 下的协议等待环。三类仍竞争同一份物理网络带宽。
这是一项显式 end-to-end admission 抽象，不宣称实现了远程 reservation 的控制协议。
native flit 只有在有限 RX 写入或预留 MC NI 缓冲接收后才 commit，credit 由原内核返回。
NoC 包化是 header+payload；fork 将 message 展开成单 flit packets，不要求与旧 Python
多 flit packet 网络逐周期一致。MC 的 HB 返回缓冲不重复计为 tile SRAM 写入。

## 两个分开报告的原生供给模型

IdealBanks 是旧独立 bank 参考的分组执行：descriptor 内每个 bank 的全部 32-byte
字分别扣减银行周期，等待最后一个字 ready，再经显式 home HB。每 bank 每 ns 一个字，
20-cycle latency；这些是假设参数，不是 WoW DRAM 标定。

Ramulator 使用已安装的 pinned HBM2 桥，保持 32 banks/M、512 MiB/M、FRFCFS、refresh
和有限控制器队列。MC 将 descriptor 按原地址展开，每 channel 每 tCK 至多提交
32 个原生字；拒绝的字保留重试。只有 descriptor 的所有 native callbacks 到齐才响应。
回调已位于 controller 的数据总线之后，所以该模式不再执行一次显式 home HB。
这与 IdealBanks 的带宽预算不同，跨 profile 的时间差不属于同硬件精度改进。

## 三种运行与证据

- B1-real：请求、返回和 dispatch/combine 使用有限 native 网络。
- B1-return-ideal：只绕过 MC-ready 后的 response NoC，保留 DRAM、有限接收写入、
  请求网络与 activation；它是返回瓶颈诊断，不是已实现的 Direct HB。
- B1-wide-NoC：只增加 compute link/flit 宽度，保留原 HB、DRAM、SRAM、owner 和图。
  C–C lane 与 bit-length 翻倍；队列字节容量保持不变。没有将未知物理项换算为总面积。

入口 `python -m w2w.experiments.run_moe_layer`，`--dram ideal|ramulator`。
每批先保存 registration、机器参数和图哈希，再依次执行三种运行。完成文件只在所有
输出完成、网络/事务/SRAM 排空、独立事件账本通过后写出。保留每个任务的 allocation、
最后 native-ready、最终 read/data delivery、compute start/finish，而不相加重叠 stall。

默认只保存事务事件；native flit 进展仍用于在线物理时隙与字节核对、逐链路计数。
`debug_flits` 可保存全部 flit 事件，但不要求正式性能运行输出全量 IPC 文本。
旧 Python CreditNetwork 仅作为小系统参考，既有 v1 读回放与 RTL 证据保持原 scope。
