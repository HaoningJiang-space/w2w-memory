# 文档索引

**开发交接入口：[HANDOFF](HANDOFF.md)** — 当前状态、复现、接口边界与下一任务。

研究问题固定为 wafer-scale memory service fabric。按所需层次阅读，不必按 Gate
时间顺序把每个实验当作新的研究题目。

## 当前实现与运行

- [服务合同改变设计选择：首轮结果](reports/CONTRACT_SELECTION_REPORT.md)
- [地址权限与物理可达性审计](reports/EGRESS_REACHABILITY_REPORT.md)
- [代码结构与依赖](CODE_STRUCTURE.md)
- [Endpoint-to-wafer：方法](methods/ENDPOINT_BRIDGE_METHOD.md) / [结果](reports/ENDPOINT_BRIDGE_REPORT.md)
- [Endpoint 合同与公开数字接口边界](methods/ENDPOINT_CONTRACT_GATE.md)
- [Git 工作流](operations/GIT_WORKFLOW.md) / [服务器存储](operations/SERVER_STORAGE.md)

## 模型、算法与历史证据

| 层次 | 方法 / 理论 | 阶段结果 |
|---|---|---|
| 初始 memory geometry | [复现说明](guides/MEMORY_README.md) | [初始报告](reports/RESEARCH_REPORT.md) |
| Bank exposure | [Bounded gate](methods/BANK_GATE_METHOD.md) | [结果](reports/BANK_GATE_REPORT.md) |
| Reciprocal exchange | [方法](methods/GUARANTEED_EXCHANGE_METHOD.md) | [结果](reports/GUARANTEED_EXCHANGE_REPORT.md) |
| Service-driven / ILP | [方法](methods/SERVICE_DRIVEN_METHOD.md) | [结果与成本](reports/SERVICE_DRIVEN_REPORT.md) |
| Matching | [方法](methods/MATCHING_PLACEMENT_METHOD.md)、[理论](theory/MATCHING_THEORY_FORMULATION.md) | [结果](reports/MATCHING_PLACEMENT_REPORT.md) |
| 小结构综合 | [方法](methods/CYCLE_CONSTRUCTION_METHOD.md) | [结果](reports/CYCLE_CONSTRUCTION_REPORT.md) |
| Sparse pooling | [方法](methods/SPARSE_POOLING_METHOD.md) | [结果](reports/SPARSE_POOLING_REPORT.md) |
| 非均匀搜索 | [方法](methods/NONUNIFORM_POOLING_METHOD.md) | [阴性结果与边界](reports/NONUNIFORM_POOLING_REPORT.md) |
| Open DSE | [方法](methods/MEMORY_FABRIC_DSE_METHOD.md) | [结果](reports/MEMORY_FABRIC_DSE_REPORT.md) |
| Slice exposure | [方法](methods/SLICE_EXPOSURE_METHOD.md) | [结果](reports/SLICE_EXPOSURE_REPORT.md) |

## 物理依据与贡献边界

- [Bank/LIO→HB 的公开证据与未知参数](background/BANK_HB_PHYSICAL_BOUNDARY.md)
- [Related work 与 claim 边界](background/BANK_RELATED_WORK.md)

历史报告的参数、提交号和结论保持原口径；只更新文件导航及可运行命令。
原始数据字节通过 `artifacts/provenance/layout_migration.json` 的 SHA-256 核对。
引用旧源码行号时仍应查看对应历史提交，不能直接套用迁移后的行号。
