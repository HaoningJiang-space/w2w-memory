# RWDL 原生服务与计算放置：完整层结果

2026-10-09，hn072 隔离目录 `/Projects/haoning/w2w-full-system-rwdl-20261008`。
从 `main@35f7e17` 延续已有系统：没有替换 kernel、BookSim 或 Ramulator，没有
Direct HB、endpoint RTL、动态迁移、预取或额外计算引擎。原始完整事件留在服务器，
配置、注册、摘要、分析、原始文件 SHA256 与构建日志已归档。

**核心结果：在这个 RWDL 候选和固定四-token 输入中，把计算放到权重分片附近，
比把权重集中返回 owner 缩短完整层时间 45.21%。** 它同时改变任务/内容放置和通信，
不能把收益拆成“纯 NoC 加速”或“纯 SRAM 写口加速”。

## 1. 原生服务：不同 memory organization 的比较

执行源 `2e3087ae1b423f169ab595699007c9369a7a081c`，`study-v4`。
保留旧返回合同，与已归档 HBM2 输入/共同机器核对；A 不重跑。

| 配置 | 完整层时间 | 最忙 memory 权重 | 原生峰值必要界 |
|---|---:|---:|---:|
| HBM2 / 4-way / streaming，历史 A | 1,064.328 μs | 28,318,464 B | 884.952 μs |
| RWDL / 4-way / streaming，B | 472.146 μs | 28,318,464 B | 207.964 μs |
| RWDL / Home / streaming，C | 519.403 μs | 56,636,928 B | 415.927 μs |

RWDL 4-way 比历史 HBM2 时间减少 55.64%，但硬件原生组织不同，不能称为同硬件优化。
在 RWDL 候选中，4-way 比 Home 仍快 9.10%；本次没有出现驻留优劣反转。
固定 owner 的最忙权重接收工作仍为 56,636,928 B，256 B/ns 的理想写口界为
221.238 μs，已超过 4-way 原生峰值界。因此只看 DRAM/NoC 两个峰值不够。

[注册与输入](../../artifacts/results/system/rwdl_service/registration.json)、
[完整分析（gzip）](../../artifacts/results/system/rwdl_service/analysis.json.gz)。
旧 HBM2 报告、九项驻留结果保持原身份；这一阶段仍包含旧本地整包/流式排空差异。

## 2. RWDL 的资源组织与时间边界

[公开 SeDRAM](https://doi.org/10.3390/electronics12051077) 给出独立 128-Mbit channel、
128-bit RWDL、3.76 ns 时钟与约 6 ns CASRD→RWDL 的依据。本项目组合成每 M
32 域 / 512 MiB，整数周期 3760 ps，接口峰值 136.170 GB/s/M；不是实测整片 WoW。

每域一条原生命令总线，ACT/PRE/RD/REF 争用，独立行状态与刷新。共 32 个 read
queue entry、32 active 和 32 refresh priority entry；没有复制 32×32 默认读队列。
每域预约最多 8 个 16 B atom，共 4096 B/M，持有到 CDC 和共享汇聚输出结束。
MC32、requester32、4 KiB descriptor、128 KiB/M 返回 staging 保持有限。

路径明确为：array digital ready → 一次 RWDL/HB beat → CDC → 256 B/ns 共享汇聚
→ Home controller staging → NoC/本地 DMA → SRAM。RWDL 与 HB 采用同一组
4096 data lane/M，不再串接旧 2048-bit 标牌总线重复收费。
保留 32 B 逻辑字映射，低/高半字以不同 16 B 原子地址服务。

原生回调保留实际 array ready 与 beat tail 时间，不能批量推进后改写成观察时刻。
新边界推进跳过无事件的 gcd=40 ps 时间点，保留每个 NoC 边界及原阶段顺序；
BookSim 的 receive/commit 仍及时处理。第一阶段 4-way 592,695 次 kernel 循环，
没有承担按 40 ps 空转的 25 倍循环数。

除公开接口锚点外，ACT/PRE、刷新和数字汇聚参数均为显式假设；完整参数及队列
生命周期见[原生合同](../methods/RWDL_NATIVE_SERVICE.md)。阵列到中心的内部线长、
controller 面积、跨域 ACT 电源限制和能耗未标定。

## 3. 新返回合同下的决定性架构对照

执行源 `1b086e0affbf6a25aa765e09ee9a9fa8e1aa25d1`，`placement-study-v2`。
三项都使用同一 36 个共享计算引擎、36×512 MiB memory、36×2 MiB SRAM、
RWDL 命令/队列、坐标 NoC、256 B flit、16-flit credit 窗口、MC32/requester32。
相同 routing、128 个专家的冻结 owner、FP8 权重/FP32 scale、BF16 输入/FP32 partial。

| 配置 | 完整层时间 | 任务数 | 权重字节 | C–C 有向 hop-flits |
|---|---:|---:|---:|---:|
| 集中 owner，streaming | **472.386 μs** | 380 | 585,248,256 | 2,584,780 |
| 集中 owner，whole | 475.192 μs | 380 | 585,248,256 | 2,584,780 |
| 靠近分片计算，streaming | **258.825 μs** | 411 | 585,248,256 | 34,918 |

集中整包/流式使用完全相同的本地 payload-beat DMA。4 KiB 本地有效数据不带
NoC header，均消耗 16 个 256 B 写周期；逐 tile 实际写口 busy cycles 也完全一致。
远端仍是 16 B message envelope＋单-flit packet。该对照只改变 native 数据可用策略，
由此引发的调度反馈允许改变实际时序。流式本次快 0.59%；不能改写历史慢 0.83% 的结果。

canonical 流式比上一阶段 472.146 μs 多 0.240 μs。这是两个明确合同的比较，包含
本地 DMA、activation/partial-state 源 SRAM 读服务与就绪策略，不称为目录整理影响。
结构整理发生在冻结实验源之后，并以独立小任务证明行为保持一致。

分片计算把每个专家的 12 个 intermediate blocks 静态分成四组，每组 3 个完整
128-wide blocks，使用其 memory 下方原有计算引擎。发送 BF16 输入、返回 FP32
partial sum，再由原 owner 归约；没有免费 multicast、复制算力或只部署激活专家。
实际引擎忙时间合计从 162.676 μs 增至 164.212 μs，增加 393,216 个归约向量操作。
引擎忙时间是多个引擎的工作量合计，不是可相加到层时间的延迟。

权重字节和每 M 工作量保持一致；远端权重 payload 由 438,936,192 B 变为零。
C–C hop-flits 减少 98.65%，已包含实际消息 header、padding、请求与合法路由。
内容布局、任务图及原生接纳顺序明确改变，行冲突 1,037,576 → 572,372；
收益不全归因于通信量，也不是 bit-exact 数值推理验证。

[注册](../../artifacts/results/system/compute_placement/registration.json)、
[资源压力与完整独立分析（gzip）](../../artifacts/results/system/compute_placement/analysis.json.gz)。

## 4. 资源压力：哪些限制实际出现？

| 独立指标 | 集中 streaming | 靠近分片 streaming | 含义 |
|---|---:|---:|---|
| 最忙 M 的原生峰值必要界 | 207.964 μs | 207.964 μs | 工作量相同；不含命令损失 |
| 最忙 compute 权重接收字节 | 56,636,928 B | 28,318,464 B | 分散消费降低汇聚热点 |
| 最忙 SRAM 写口实际服务 | 234.966 μs | 112.788 μs | 含所有接收字节及分片取整 |
| 最忙 C–C link | c23→c17，127,399 flits | c3→c9，1,319 flits | 各自 layer 平均占用 26.97% / 0.51% |
| 单 source 最大 ready-head credit 等待 | c23，302.132 μs | c2，2.248 μs | 源注入机会计数，不能直接等于长线 stall |
| 有 credit 但队头未供数、后方有 ready 消息 | c17，10.452 μs | c3，0.367 μs | FIFO 策略阻塞；没有修改仲裁器 |
| 单引擎最大计算 busy / 层时间 | 3.21% | 2.98% | 未显示计算引擎吞吐饱和 |
| 最忙源 SRAM 读口服务 | 3.264 μs | 1.792 μs | activation/状态显式服务；权重内读包含在计算假设 |
| CDC/汇聚已就绪数据峰值 | 512 B/M | 512 B/M | 不代表整个预约空间只需 512 B |
| 预约空间拒绝尝试 | 0 | 0 | 4096 B/M 原生到汇聚预算未饱和 |

集中任务 `expert52/tile11` 在 460.566 μs 分配，470.247 μs 最后 controller-ready，
471.099 μs 读交付，471.520 μs 计算结束。它自己的未供数等待合计 103 个 source
周期，其中 ready-behind 3 个；这不能支持“该任务主要被 streaming HOL 拖慢”。
近分片最后专家输出经 `expert62/reduce`，257.904 μs 开始、257.952 μs 完成。
完整层还须等待输出返回与最终 combine，不能拿专家完成时间替代层时间。

在两种放置下，最后 RWDL/HB tail 分别是 470.244400 μs / 257.022320 μs。
因此“最后 native-ready 接近层结束”不独立证明系统仍纯 DRAM-bound：blocking tile
和传输反压也会推迟后续读接纳。必须结合映射变化与资源压力判断。

当前结果支持**集中权重消费形成了显著的系统限制，普通静态分块可保留更多空间并行度**。
它没有单独证明窗口偏小、RX 独占主瓶颈，或固定 owner 在所有请求/时序下都较差。
写口忙服务、队列等待、原生拒绝尝试与 FIFO 计数互相重叠，不相加成总 stall。

## 5. 成本边界与下一项决策

单-flit cell 声明 64-bit sideband：src/dst 6/6、class 2、tag 16、ordinal 8、
有效长度 10、首尾 2、保留 14。使用有限 65,536 tag 池；simulator 内部全局 ID
和 path history 不作为免费物理字段。相同机器两种放置成本完全一致：

| C–C 资源代理 | Data | Sideband |
|---|---:|---:|
| wire bit·mm | 7,274,496 | 227,328 |
| pipeline bits | 3,809,280 | 119,040 |
| 有向 C–C 输入缓冲 bytes | 491,520 | 15,360 |

这不是完整面积账：local router port、控制器、SRAM bank、仲裁与内部走线未完成
物理标定。远端接收位置和 tag 的预约仍为理想全局参考，没有控制消息/RTT。
一个 aggregate tile 代表一份共享服务资源，不是一颗真实物理 core；禁止把任意
缩小 reticle 当作同资源面积 DSE。几何缩放只能显式作为距离敏感性。

**当前应优先保留计算放置这个强基线。** 若下一轮要定位集中方案的 credit 原因，
只增加一个按 RTT 配平并计 input/ejection/sideband 缓冲成本的 B1 对照；不用先加宽
链路，更不需要 Direct HB。native 参数/请求规模的交叉点仍待后续少量固定对照，
本报告给出一个 136.170 GB/s 候选下的实测点，不声称完整转折曲线已测完。

## 6. 证据与复现

两阶段均完整排空、36,578,016 个 16 B atom 守恒，并独立核对事件、任务、SRAM、
MC/outstanding/NI 与原始返回字节。canonical 分片有 143,220 个 descriptor，集中
为 144,336；这是不同分块的尾片取整，完整权重字节相同。

[原始文件身份与归档索引](../../artifacts/provenance/rwdl_service/study/archive-index.json)
记录执行 SHA、分析 SHA、结果 SHA256、构建 manifest 和原始目录。
每分钟的只读检查日志已保存，所有任务结束后检查器自行退出。
原始 `result.json.gz` 不入 Git；已压缩输入/摘要/分析可解压查看。

```sh
# 在 hn072、冻结 source 与原始 study 完整存在时，独立重算：
python -m w2w analyze_rwdl_study --source <study-v4> --output <new-analysis.json>
python -m w2w analyze_compute_placement --source <placement-study-v2> --output <new-analysis.json>
```

运行新实验使用新目录与新 commit 注册，不在旧执行源中更新代码或复用旧目录。
