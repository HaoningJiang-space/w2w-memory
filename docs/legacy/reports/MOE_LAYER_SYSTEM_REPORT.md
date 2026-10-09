# 完整 routed MoE 层：已有 compute 网络之后，返回直连是否值得？

2026-10-09；执行服务器 hn072（ee4e072）。六项执行源码固定为
`3a498c1b9347e298e7c5766885069d8d57ddf9ba`，记录分析为 `719b61b`。

**完整链已执行：真实 token routing → dispatch → 分块权重请求 → 原生服务 →
返回/SRAM 写入 → expert 计算 → combine。** Native BookSim 复用现有实现，
`SystemExecution` 仍是唯一任务与事务调度器。

这次结果支持一个具体研究判断：在当前 HBM2 配置和单 token 输入下，优先研究
MC/DRAM 服务与静态驻留。理想化返回和加宽 NoC 都未缩短本层时间；在独立 bank
的高供给参考下，两种改动却有效。额外 memory attachment 的价值取决于原生服务
与闭环请求，不由局部 endpoint 面积或物理可达方向数决定。

## 1. 同一任务的六项结果

主指标为本层 combine 完成时间。括号内为相对同一 DRAM profile 的 B1-real
完成时间变化，负数表示更快。

| 条件 | IdealBanks | Ramulator HBM2 |
|---|---:|---:|
| B1-real：请求、返回、激活经过有限网络 | 170.899 μs | 681.736 μs |
| B1-return-ideal：只绕过 MC-ready 后的返回 NoC | 131.631 μs（−22.98%） | 712.581 μs（+4.52%） |
| B1-wide-NoC：compute link/flit 位宽翻倍 | 139.675 μs（−18.27%） | 691.823 μs（+1.48%） |

三条件使用同一 owner、驻留、地址、计算量、SRAM、DRAM 与 HB 预算；宽 NoC
固定 router/NI 缓冲字节预算，flit 数减半。理想返回仍保留有限接收和 SRAM 写入，
是一项诊断干预，未实现可制造 Direct HB。它也不是对所有闭环调度的时间上界。

两列**不是同硬件的快模型与精确模型**。IdealBanks 给予 32 banks/M 各自每 ns
一个 32-byte 字，之后另有 256 B/ns home HB；HBM2 是有原生命令和共享总线的
参考 channel，其回调已包含原生数据总线。因此只在各列内部作架构比较。

每项均完成 98 个任务、37,056 个 descriptor、4,719,744 个 native words，
读取 151,031,808 B 权重；请求、返回、数据依赖、SRAM、MC 和网络全部排空。
实际运行耗时分别为 97.52/65.04/80.82 s 和 228.20/161.05/178.24 s。

## 2. 输入、任务与机器是什么

使用已有 Qwen3-235B-A22B-FP8/MMLU routing 中 `c0_b1` 的第一个请求、layer 0、
第 17 个 decode step（1-based）。该 token 选择 `[36,10,23,108,62,67,109,50]`，
不重新采集、不按实验结果选 owner。沿用训练期冻结的 marginal LPT owner。
模型形状及量化来源为[官方配置](https://huggingface.co/Qwen/Qwen3-235B-A22B-FP8/raw/main/config.json)。

hidden=4096、expert intermediate=1536。每 128-wide intermediate block 读取
up/gate/down FP8 权重与 FP32 scales，再计算部分和；12 个 block 顺序执行。
BF16 激活 dispatch 和 combine 返回各 65,536 B。完整 DataEdge 总量 2,293,760 B
还含同 tile 上 block 间的输入与 FP32 累加状态，不把它们全部计作跨 compute 流量。

所有 128 个 expert 的对象在开始前驻留，每个 block 一半放 owner home memory，
另一半放相邻 `owner XOR 1` memory。实际执行按 64 KiB 段交错读取 home/peer；
没有复制或迁移。各运行图哈希均为
`105bd4bb16bbcf6142fac830952f13c0a05eaa5a1408ae307ceca8c1d9392eb2`。
记录分析进一步比较了每个 task/memory/bank/address/bytes 的集合，六项一致。

机器为 6×6 compute mesh、36 reticles、每 reticle 一个聚合 tile/engine/MC；
36 个 32-bank memory，每 M 512 MiB。显式允许 stitching，memory 不充当 router。
每 tile 2 MiB SRAM，4096 MAC/ns、256 vector ops/ns；基线 C–C 256 B/ns，
3-cycle router、2-cycle link；写 SRAM 256 B/ns。每 tile 最多 32 个 4 KiB
outstanding、每 cycle 发起至多四个 descriptor，每 MC 32 个事务槽。

这是**一个 routed FFN 子层的参数化时序模型**，起点为已驻留的输入，终点为
combine 完成。计算性能尚未标定；不包含 routing projection、attention、KV、
整模型服务，也不验证数值输出。详细分块、时钟和缓冲合同见
[MOE_LAYER_SYSTEM](../methods/MOE_LAYER_SYSTEM.md)。

## 3. HBM2 为什么没有因返回加快而获益

三个结果的最后一个 expert 任务均为 `expert62/tile11`：

| 事件/间隔 | B1-real | 理想返回 | 宽 NoC |
|---|---:|---:|---:|
| 任务分配时刻 | 623.198 μs | 652.505 μs | 635.095 μs |
| 最后 native-ready 时刻 | 680.492 μs | 711.337 μs | 690.820 μs |
| 最后 read-delivery 时刻 | 680.494 μs | 711.339 μs | 690.837 μs |
| 计算结束 | 680.915 μs | 711.760 μs | 691.258 μs |
| 分配至最后 native-ready | 57.294 μs | 58.832 μs | 55.725 μs |
| 最后 native-ready 至最后 read-delivery | 2 ns | 2 ns | 17 ns |

这组时间定位的是最终 expert 的尾部，不能把各 task 的重叠等待相加成整层 stall。
Descriptor native-admission→ready 包含尚未展开的 native words 和控制器排队，
不是孤立的 DRAM command latency。

| 整层统计 | B1-real | 理想返回 | 宽 NoC |
|---|---:|---:|---:|
| 平均 native-ready→read-delivery | 31.24 ns | 18.16 ns | 23.81 ns |
| 平均 read-issue→MC-accept | 29.88 ns | 116.16 ns | 51.01 ns |
| 平均 descriptor native-admission→ready | 3.273 μs | 3.230 μs | 3.268 μs |
| 最忙 C–C link 整层平均利用率 | 6.09% | 0.33% | 3.34% |
| native read row conflicts | 201,542 | 217,916 | 212,013 |

返回阶段确实变短，但更早释放 outstanding 会改变随后发起和接纳的请求。
四个双倍负载 memory（m14/m15/m32/m33）的 descriptor 接纳次序哈希都改变了。
其中 Channel 15 的 read row conflicts 从 29,140 增至 45,780；原生统计的
平均 read latency 从 53.605 增至 55.898 tCK。其他流与 FRFCFS/refresh 也在同一
时间线上反馈。这些观察说明服务序列和行局部性确实改变；本轮没有用固定命令
顺序的反事实实验将全部 30.845 μs 增量归因于某一个因素。

平均链路利用率不能排除短时拥塞，但结合两项网络干预以及关键任务时间线，
已有证据不足以支持在这个配置上增加 Direct HB。理想返回的负结果保留，
不能删除它或把平均带宽倒数当作任务时间。

## 4. 更值得继续改变的是哪一项资源

只有 12/36 个 memory 收到此次权重请求：

| Memory | 每 M 必需读取字节 |
|---|---:|
| m14、m15、m32、m33 | 18,878,976 B |
| m12、m13、m16、m17、m18、m19、m30、m31 | 9,439,488 B |
| 其余 24 个 | 0 B |

四个热点 memory 的 MC 事务槽均达到 32；所有活动 requester 的 outstanding
也达到 32。计算 tile 的 SRAM 峰值为 1,647,488 B，未靠扩大 SRAM 容纳整专家。
这里同时存在原生共享资源、有限请求窗口与固定字节不均衡，尚未分离各自贡献。

从 DRAM 角度，32 banks 提供命令/阵列并行度，不等于拥有 32 条独立数据总线。
从 wafer 角度，闲置 memory 只有预先存了所需字节才有用；增加接线不改变这个条件。
下一项同任务对照应保持 NoC/HBM2/计算/SRAM，选择一个因素：原生服务域内的
静态字节分配，或固定地址集合下的 controller admission 次序。先用当前事件账本
区分 MC 前排队、descriptor 展开及 native 供给，不同时放开所有设计变量。

这是本轮之后的研究动作，尚未声称新的驻留或调度已改善完成时间。当前一 token
不足以推广到连续 batch；后续独立 cohort 要提前选定，继续保持对象驻留冻结。

## 5. 网络成本与建模边界

| 制造资源 proxy（整机、有向链路） | 基线 | 宽 NoC |
|---|---:|---:|
| C–C lane bits | 245,760 | 491,520 |
| HB lane bits | 147,456 | 147,456 |
| 总 wire bit-mm | 2,460,549.12 | 4,918,149.12 |
| 总 pipeline bits | 638,976 | 1,130,496 |

宽 NoC 增加物理线和流水，缓冲字节不增加；这些不能未经标定换成面积或能耗。
HBM2 回调在 controller payload-ready，已包含原生总线，因而不会重复计 home HB
传输；物理账本仍保留该 attachment。没有新增 RTL/P&R，未把历史 endpoint 面积
拼成这个系统的成本。

有限接收空间在 admission 时预留，以避免一 VC 的协议等待环。这是显式的端到端
admission 抽象，未实现远程 reservation 控制包。Native fork 将消息展开为单 flit
packets；SRAM 按每个 flit 的有效字节向上取整收写周期，宽 flit 没有额外的跨 flit
合并优化。Native 每跳带宽、有限缓冲、credit、接收 commit 仍由复用内核推进。
这些边界适用于三条件，需随未来物理实现进一步校准。

## 6. 复现与归档

运行根目录：`hn072:/Projects/haoning/w2w-full-system-20261009`。
`source_3a498c1` 是干净执行工作树；`wafer-runtime` 是固定版本 wrapper 与必需
vendor Python 文件的干净 sparse/partial checkout，不宣称另一次全项目构建。
BookSim 二进制复用原验收产物，SHA-256
`560d9fd342aa733d62d3158fc4330ac66db488bbf2376e8df7f1ff2a60c0ea56`，
wrapper pin `0c56c24b4bf602b8b2c036681f526971305dde99`。
Ramulator pin `72427a1bba3771564c4fb0e494ba02242fd1eaa7`；ABI/配置哈希在每份结果。

```sh
# 在 hn072 的上述运行根目录，选择新的、不存在的 output 名称
cd source_3a498c1
W2W_PY=/Projects/haoning/w2w/.venv/bin/python
$W2W_PY -m w2w.experiments.run_moe_layer \
  --booksim-source ../wafer-runtime --booksim-binary ../booksim/endpoint_booksim \
  --dram ideal --output ../layer-ideal-reproduction

PYTHONPATH=/Projects/haoning/w2w-tools/ramulator2-72427a1/python \
W2W_RAMULATOR_BRIDGE=/Projects/haoning/w2w/build/dram_bridge/_w2w_ramulator.cpython-310-x86_64-linux-gnu.so \
$W2W_PY -m w2w.experiments.run_moe_layer \
  --booksim-source ../wafer-runtime --booksim-binary ../booksim/endpoint_booksim \
  --dram ramulator --output ../layer-hbm2-reproduction

# 分析无需启动模拟器；在含分析命令的 719b61b 或后续源码中运行
$W2W_PY -m w2w analyze_moe_layer \
  --source ../layer-ideal-3a498c1 --source ../layer-hbm2-3a498c1 --output ../analysis-reproduction.json
```

- [分析及原始文件路径/大小/哈希](../../artifacts/results/system/moe_layer/analysis.json)。
- [输入、完整参数、摘要、完成标志](../../artifacts/results/system/moe_layer/)。
- [交付清单与源码身份](../../artifacts/provenance/moe_layer_system/delivery.json)。
- [原生回归日志](../../artifacts/provenance/moe_layer_system/native-regression.log.gz)：既有
  system execution 与 DRAM tests 共 34 项通过、0 skip；未新增 BookSim 验收 campaign。

六份完整压缩事件记录保留 hn072，各约 3.6–4.8 MB。初次 `6578ee6` 运行将 MC HB
buffer 误计为 tile SRAM 写入，已在 `3a498c1` 修正后重新运行，初次结果不进入此表。
文档/分析提交没有改写执行源码、输入或已完成记录。

eex005 的九个停用 W2W 工作树经归档、目标端校验和恢复后退役，观测释放 1.68 GB；
其证据与本次系统结果分开保存于[服务器清理记录](../operations/SERVER_STORAGE.md)。
