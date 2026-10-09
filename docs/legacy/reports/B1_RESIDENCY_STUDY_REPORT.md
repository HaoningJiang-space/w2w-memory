# 既有 compute NoC 上的静态驻留：Home、Pair 与 4-way

2026-10-09，hn072。**本报告回答当前 36-channel HBM2 reference＋合成 6×6 stitched
mesh 的完整 routed FFN 层时序，不是经过物理校准的 WoW 架构结论。**
原生服务边界与整 descriptor 返回假设保持冻结；后续修正另给机器/模型身份。

## 结果：先建立更强的 B1，再判断额外 memory fabric

单位为 μs；降低比例按层完成时间计算，各行不合并为平均应用加速。

| 输入 | Home-only | Pair | 4-way | 4-way 比 Pair 缩短 | 4-way 比 Home 缩短 |
|---|---:|---:|---:|---:|---:|
| c0_b1，原单 token | 661.173 | 681.736 | 347.679 | 49.00% | 47.41% |
| c1_b1，独立单 token | 661.163 | 681.726 | 524.448 | 23.07% | 20.68% |
| c2_b4，预定四 token | 1,981.770 | 1,706.464 | 1,041.569 | 38.96% | 47.44% |

两个单 token 的 Pair 都比 Home 慢约 3.11%。Pair 虽增加活跃 DRAM 数，却没有降低
最忙 channel 的必需字节；新增远端访问及原生访问顺序改变并未换来更短层时间。
4-way 在两个单请求和四 token 下均比 Pair 更快，说明已有 compute NoC 可以兑现
更分散的静态权重驻留。这尚不证明 Direct HB 必需，也不证明其在别的原生组织下无用。
四 token 中 Pair 比 Home 缩短 13.89%，此时其峰值 channel 字节确实降低；不能从
两个单 token 的负结果推导 Pair 在所有需求下都无效。

Home-only 固定相同 expert owner，仅将权重全部放回该 owner 的 memory；仍实际执行
dispatch/combine。它是隔离驻留的强对照，不声称已优化所有可能的 Home placement。

## 对照固定了什么

沿用 [完整层合同](../methods/MOE_LAYER_SYSTEM.md) 的 Qwen3-235B-A22B-FP8、layer 0、
decode step 17（1-based），routing 决定 token→expert；同一 cohort 的任务、owner、
计算量、SRAM、MC、NoC 与总权重读取字节相同。只改变全部 128 个 expert 的静态驻留。

- Home：全部放在 owner；Pair：各一半在 owner 与水平 `owner XOR 1`。
- 4-way：各四分之一在 owner 所属固定 2×2 区域；规则只依赖坐标，不读取本轮 expert 集。
- 三个 cohort 对每种 policy 使用完全相同的全体 expert 对象布局/哈希，不逐请求重放置。
- 保留 64 KiB 分配段、4 KiB descriptor、每 tile/cycle 4 个发起槽、outstanding32、
  MC32 和 2 MiB SRAM。每 expert 的 12 个 blocking compute tiles 不变。
- 短尾和 header/padding 如实收费：单 token 的 Home/Pair/4-way 分别有
  36,960 / 37,056 / 37,248 个 descriptors，不用额外请求槽补偿 4-way。
- BookSim、Ramulator pin、二进制、native 配置和全部物理网络预算相同。仅 native
  config 中每次运行的 trace/report 文件名不同；分析保存原哈希并比较其余全部参数。

单 token 各选择 8 个 experts，98 个任务，读取 151,031,808 B；四 token 选择 31 个
不同 experts，380 个任务，读取 585,248,256 B。同 batch 内共享专家权重，未把
32 次选择直接算成 32 份冷权重。逐 token routing 与所有输入 SHA 在归档中。

Pair/4-way 六项在执行前一起注册。主请求产生信号后，按注册选取 c1_b1 与 c2_b4，
没有按结果挑样本。Home 是用户随后要求的对照，单独注册，未回写原六项注册。
独立请求来自既有 corpus 的不同组，未与本轮主请求重合；不称为新采集数据集。

## 原生负载改善与通信代价

MB 使用十进制。NoC wire MB 为 native 实际 flit-hop×256 B，包含 request、response、
activation、header 和 padding；不是逻辑 payload 或最短路径估计。Home 的跨 compute
流量为激活/结果，本地权重仍经过 native、有限本地 DMA 和 SRAM 写端口。

| 输入/布局 | 活跃 M | 峰值 M 字节，MB | NoC wire MB | 最忙有向链路平均利用率 |
|---|---:|---:|---:|---:|
| c0 Home | 8 | 18.879 | 0.714 | 0.025% |
| c0 Pair | 12 | 18.879 | 85.698 | 6.09% |
| c0 4-way | 20 | 9.439 | 170.780 | 13.50% |
| c1 Home | 8 | 18.879 | 0.609 | 0.022% |
| c1 Pair | 14 | 18.879 | 85.593 | 6.09% |
| c1 4-way | 24 | 14.159 | 170.675 | 9.72% |
| c2 Home | 19 | 56.637 | 2.698 | 0.016% |
| c2 Pair | 26 | 47.197 | 332.010 | 7.16% |
| c2 4-way | 32 | 28.318 | 661.704 | 12.54% |

4-way 相对 Pair 的峰值必需字节在三组分别降低 50%、25%、40%；层时间分别降低
49.00%、23.07%、38.96%。这种对应支持原生负载分散的解释，但不是一般预测公式：
对象分块、MC 排序、行状态及任务依赖仍参与执行。
额外 NoC wire 流量约增加 99.3%；本轮没有增加物理线宽或 buffer。平均链路利用率
不能排除短时拥塞，也不等于未来高供给机器仍有同样余量。

## 等待发生在哪里

| 输入/布局 | MC/native 接纳到整 descriptor ready 平均，μs | ready 到交付平均，ns | read row conflicts |
|---|---:|---:|---:|
| c0 Home | 4.346 | 16.97 | 146,818 |
| c0 Pair | 3.273 | 31.24 | 201,542 |
| c0 4-way | 1.897 | 54.49 | 198,445 |
| c1 Home | 4.346 | 16.97 | 146,844 |
| c1 Pair | 2.720 | 31.23 | 167,004 |
| c1 4-way | 1.914 | 55.80 | 189,621 |
| c2 Home | 4.347 | 16.97 | 568,663 |
| c2 Pair | 3.169 | 31.08 | 746,942 |
| c2 4-way | 2.208 | 52.21 | 790,146 |

native 等待包括 descriptor 展开、队列和命令执行，不是单次 DRAM read latency。
Home 的全体 descriptor 平均等待可以高于 Pair，但关键完成时间更短；平均请求
时间不能替代同步层 makespan。c1/c2 的 4-way 行冲突反而增加，仍然整体更快，
收益也不能归因于“更好的 row locality”。完整逐 MC 分布保存在分析 JSON。

末尾 expert tile 的“分配→最后 native-ready”在 c0 从 57.294 降到 27.801 μs，
c2 从 27.337 降到 14.986 μs；最后 native-ready 到该 tile 最后读交付分别为
2→49 ns、33→42 ns。这是关键尾部的事件证据，不是把所有并行 stall 相加为层时间。
当前结果没有表明新增专用返回硬件应优先于原生组织和现有路径的准确建模。
所有运行的峰值 MC/outstanding 均为 32；两个单请求的 SRAM 峰值为 1,647,488 B，
四 token 为 1,721,728 B，三种驻留相同。没有为 4-way 增加接收工作集容量。

## 机器与返回语义的明确边界

1. 36 个独立 HBM2 reference channels，512 MiB/M，32 banks/M，两个 pseudochannels/M；
   公共命令/数据资源已模拟，不是 32 个独立无限原生出口。HBM2 callback 位于 controller
   payload-ready，已包括 native bus；本轮没有再次显式走 Home HB。
2. 6×6 stitched mesh 的 10 mm、2-cycle link 与 256 B/ns 是参数假设，未由实际 reticle
   placement 和工艺布线导出。不能与旧 no-stitching H/plus 机器混为同一物理架构。
3. 本轮采用整 descriptor 返回：其全部 32 B native words 完成后才开始 NoC supply。
   细粒度流式可改变重叠与请求反馈，性能及布局排名尚未在该语义下复测。
4. 三种 policy 的全体权重均为 2,416,508,928 B，总 DRAM 为 19,327,352,832 B，
   容量占用 12.503%；单 M 最大 75,515,904 B、14.066%。这是冷读带宽分布实验，
   尚未代表完整模型容量压力、持续 batch serving、完整 LLM 或数值推理。

后续只按 [Wafer machine 与流式返回合同](../methods/WAFER_MACHINE_CLOSURE.md)推进：
用实际坐标生成路径/时延/成本，保留 native 边界的含义，再实现有限部分供数。
高并行度原生组织按独立通道、容量、时序及 HB 资源构造；不把 HBM2 带宽直接调大。
不扩大驻留 DSE，不开发新的 RTL 或先预设 B2 为赢家。

## 复现与证据

- Pair/4-way 执行源码 `fb23c3caa558540b99d2f474af0fe54d40b82418`；Home 源码
  `c9599bdb9654a668c68c36fa8a80bcf59167c387`；分析源码 `b0aeb4b`。
- native BookSim source `0c56c24b4bf602b8b2c036681f526971305dde99`；Ramulator
  `72427a1bba3771564c4fb0e494ba02242fd1eaa7`；二进制/配置 SHA 保存在结果身份中。
- 服务器根 `/Projects/haoning/w2w-full-system-residency-20261009`，`study/` 和
  `home-study/` 分别保存注册、冻结输入、完整事件、摘要和退出状态；运行源码树保持冻结。
- [协议](../methods/B1_RESIDENCY_STUDY.md)；[分析与紧凑结果](../../artifacts/results/system/b1_residency/)；
  [溯源与日志](../../artifacts/provenance/b1_residency/)。完整事件留在服务器，归档记录其
  文件字节数和 SHA256，不因报告或物理设计文档修改执行结果。
- 37 项相关回归在性能运行前通过，无 native skip；原 Pair 图/机器与旧实验一致，
  c0 Pair 完成时间也重现 681.736 μs。分析不启动新性能运行。
- 九项均退出码 0、完成独立事件审计及全部事务/网络 drain；每项完整 native 字节与
  逻辑读字节相等。压缩归档在服务器逐项解压后与源记录核对，再同步到 Git。

在对应固定提交的独立工作树，使用已有 Python 环境、Ramulator bridge 与 BookSim：

```sh
python -m w2w run_residency_study --prepare --output <study>
python -m w2w run_residency_study --output <study> --case c0_b1-pair \
  --booksim-source <pinned-wrapper> --booksim-binary <existing-binary>
# 对原注册其余五项逐项运行；Home 在其源码树单独 --prepare --policies home。
python -m w2w analyze_residency_study --source <study> \
  --home-source <home-study> --output <analysis.json>
```

运行环境、实际命令、测试与每项完成记录见归档。只在 hn072 实验；未修改其他
开发者的 RTL/wafer_simulator 工作树，未在 eex005 新增实验。
