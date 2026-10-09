# W2W Memory-on-Logic 当前交接

2026-10-09：计算并行度匹配对照、独立服务定义与有限controller窗口对照已完成。
**当前结果：[计算局部性与服务配平](reports/COMPUTE_LOCALITY_SERVICE_BALANCE_REPORT.md)。**

| 固定 c2_b4 四 token | 集中 / μs | 远端四链 / μs | 近分片 / μs |
|---|---:|---:|---:|
| 历史 q1/FIFO，原计算吞吐 | 472.386 | **307.813** | **258.825** |
| q4/窗口4 round-robin，显式权重读 | 544.581 | — | 341.507 |
| q4/窗口4 row-batched，显式权重读 | **463.263** | — | **258.830** |

远端四链与近分片的图、内容/地址、逐引擎工作量和tensor传输保持一致，只将block
计算在固定2×2组内顺时针轮换一跳：就近减少15.915%，不能把原45.209%全归为局部性。
有限行选择策略下，集中/近分片仍相差44.129%。队列扩大加简单轮转反而变慢，
负结果也归档；controller调度不是RWDL接口固有属性。

## 下一项任务

本轮P0匹配对照与P1原生服务解释已交付；P2已提供明确资源预算和粗空间成本参考，
仍未完成物理标定。停止目录整理和新的完整层矩阵，不增加endpoint、Direct HB、
动态伙伴、prefetch或一般DSE。

下一项先为**计算SRAM与内部汇聚的实现预算**找依据：核对32个64KiB bank、
每bank128B/cycle计算读与独立外部读/接收写的macro/数据通路成本；核对domain-local
HB落点到中心的有限收集路径。当前4.096TB/s供数是显式候选，不是已验证的物理实现。
粗8×4域布局的线长/寄存器仅为成本参考，没有进入已测时间。

若继续隔离通信硬件影响，只对匹配四链的远端方案增加一个按RTT配平且完整计缓冲
成本的B1对照，保留相同图/地址/计算供数；不能拿改变计算结构的集中方案直接证明
某条链路缺口。新实验需有明确决策问题，不为制造网络瓶颈而提高原生峰值。

## 服务边界与代码

[目录/依赖](CODE_STRUCTURE.md) · [结构整理记录](reports/STRUCTURE_REFACTOR_REPORT.md)

| 内容 | 入口 |
|---|---|
| interface / array timing / controller / aggregation / compute供数 | `machine/service_profiles.py` |
| 权威有效RWDL/HB资源，排除旧routing-only HB标牌 | `service_profiles.effective_resources()` |
| 分片与固定顺时针匹配对照 | `workloads/moe_partition.py` |
| 统一时间、事务与资源生命周期 | `system/kernel.py` |
| 本地DMA / 唯一接收写口 | `system/local_dma.py` / `receive_write.py` |
| 原生命令、显式刷新相位、16B地址与有限CDC/汇聚 | `service/dram` / `memory/rwdl_backend.py` |
| NoC供数、注入、接收与commit | `network/booksim_backend.py` / `native_booksim` |
| 当前配方 / 守恒、匹配与条件服务参考分析 | `run_compute_placement` / `analyze_compute_placement` |
| 原生行命中/跨行例子 | `tools/native_rw_dl_reference.py` |
| 未进入运行时的内部线成本参考 | `machine/rwdl_layout.py` |
| 构建 | `tools/build_native.py`；[独立工具链](methods/NATIVE_TOOLCHAIN.md) |

[RWDL合同](methods/RWDL_NATIVE_SERVICE.md)与[放置合同](methods/COMPUTE_PLACEMENT_CONTRACT.md)
明确就绪位置和剩余传输段。计算权重读与外部256B/ns端口分开；tile至少满足权重
读取/算术两者的最大值，再执行向量阶段。理想全局接收/tag预约、blocking tile、
源FIFO与折叠中央汇聚仍保留。资源代理不等于PPA，不声称WoW物理服务已闭合。

原生接口峰值136.170GB/s；连续跨行小例子119.382GB/s。旧近分片实际行/刷新
计数的条件服务参考248.663840μs，距完成10.161160μs；这些计数依赖已执行trace，
不能升级为不随调度改变的普适下界，或将剩余全部称为网络可优化空间。

## 冻结证据与协作

hn072根目录 `/Projects/haoning/w2w-full-system-rwdl-20261008`：
`rotation-source@492affaa` / `rotation-study-v1`，`service-source@123c4e1` /
`service-study-v1`，`service-row-source@e41214c` / `service-row-study-v1`。
五项新增完整层全部排空；原三项只读复用。每分钟检查器随完成退出。

[本轮身份与核验索引](../artifacts/provenance/service_balance/archive-index.json)记录执行/分析
SHA、原始结果SHA256、native manifest与配置/摘要/负结果；raw事件留服务器。
旧`source@2e3087a`/`study-v4`与`placement-source@1b086e0`/`placement-study-v2`
不更新。[旧RWDL/放置报告](reports/RWDL_COMPUTE_PLACEMENT_REPORT.md)保留原身份。

源码本地编辑，只维护main、Git同步；构建、测试、实验只在hn072隔离目录。
旧eex005仅证据迁移与已核验清理；不修改其他开发者的RTL或`wafer_simulator`。
凭据、native二进制、环境与原始capture不入Git。
