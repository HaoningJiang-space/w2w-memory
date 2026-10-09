# W2W Memory-on-Logic 当前交接

2026-10-09：独立 RWDL 与同资源计算放置对照已完成，结构整理 A/B/C 已提交并核验。
**当前结果：[RWDL、计算放置与资源压力](reports/RWDL_COMPUTE_PLACEMENT_REPORT.md)。**

| 冻结输入 c2_b4 | 完整层时间 |
|---|---:|
| 初版 RWDL / 4-way，旧返回合同 | 472.146 μs |
| 初版 RWDL / Home，旧返回合同 | 519.403 μs |
| 统一本地 DMA / 集中 owner / streaming | 472.386 μs |
| 同图同资源 / whole | 475.192 μs |
| 靠近权重分片计算 / streaming | **258.825 μs** |

分片计算比 canonical 集中流式缩短 45.21%，36 个引擎共享、原生 memory 工作量
相同，额外计输入分发、源 SRAM 读、FP32 partial 与归约。当前实测点支持保留
计算放置这个强基线；还不能宣称某个单独 RX/credit 资源解释了全部时间差。

## 下一项任务

不再扩 endpoint、Direct HB、动态伙伴、prefetch 或一般 DSE。
若继续诊断集中方案，只做一个按实际 RTT 配平且完整计缓冲成本的 B1 对照，
并保持源/目的 SRAM、cell 格式、native 与任务图一致。先区分注入/credit 与接收
写口的因果限制，再决定是否需要新 attachment。原生时序/请求规模的转折曲线
尚未测完；当前不是已校准 WoW 产品的最优设计结论。

## 代码与合同

[当前目录/依赖](CODE_STRUCTURE.md) · [结构一致性记录](reports/STRUCTURE_REFACTOR_REPORT.md)

| 内容 | 入口 |
|---|---|
| 机器资源 / 坐标与成本代理 | `w2w/machine/presets.py` / `geometry.py` |
| routing 选择 / 纯任务编译 | `workloads/routing_input.py` / `moe_task_graph.py` |
| 统一时间、事务与资源生命周期 | `system/kernel.py` |
| 本地 DMA / 唯一共享接收写口 | `system/local_dma.py` / `receive_write.py` |
| 原生命令、刷新、16 B 地址与 CDC/汇聚 | `service/dram` / `memory/rwdl_backend.py` |
| NoC 供数、注入、接收与 commit | `network/booksim_backend.py` / `native_booksim` |
| 当前配方 / 离线资源压力 | `run_compute_placement` / `analyze_compute_placement` |
| 原生服务配方 / 分析 | `run_rwdl_study` / `analyze_rwdl_study` |
| 构建 | `tools/build_native.py`；[独立工具链](methods/NATIVE_TOOLCHAIN.md) |

[RWDL 合同](methods/RWDL_NATIVE_SERVICE.md) 区分 array-ready、RWDL/HB beat、CDC、
共享汇聚与 controller-ready；RWDL/HB lane 不重复收费。聚合 tile 内部面积/距离
未标定，接收与 tag 预约仍是理想全局参考；不能称物理服务已完全闭合。

## 冻结证据与协作

源目录与结果都在 hn072 `/Projects/haoning/w2w-full-system-rwdl-20261008`：
`source@2e3087a` / `study-v4`；`placement-source@1b086e0` / `placement-study-v2`。
完整运行排空，原始事件留服务器；每分钟检查器已随三项完成自行退出。
[归档索引](../artifacts/provenance/rwdl_service/study/archive-index.json) 给出原始 SHA256、
native manifest、分析版本和已压缩配置/摘要；冻结源与结果不更新。

本地编辑，只维护 `main`，通过 Git 同步；构建、测试、实验只在 hn072 隔离目录。
旧 eex005 仅用于证据迁移与已核验清理。不修改其他开发者的 RTL 或
`/Projects/haoning/wafer_simulator`。凭据、raw captures、native 二进制与环境不入 Git。
旧 [HBM2 驻留](reports/B1_RESIDENCY_STUDY_REPORT.md)、
[几何/流式结果](reports/WAFER_MACHINE_CLOSURE_REPORT.md) 保持原身份。
历史 read-only/RTL 为组件证据；[全部历史索引](README.md)。
