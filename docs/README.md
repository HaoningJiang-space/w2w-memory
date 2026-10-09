# 当前文档

Architecture V3 研究给分布式 Compute Wafer 增加垂直 DRAM 后的接入、消费与通信组织。

- [P0–P6 交付与完整层结果](reports/ARCHITECTURE_V3_REPORT.md)
- [架构与对象边界](ARCHITECTURE.md)
- [物理假设与参数来源](PHYSICAL_ASSUMPTIONS.md)
- [执行合同与模型限制](SIMULATOR.md)
- [Central / Distributed / External 基线](BASELINES.md)
- [当前源码地图](CODE_STRUCTURE.md)
- [交接与复现入口](HANDOFF.md)
- [研究范围](RESEARCH_SCOPE.md)

历史报告、理论与旧实现说明保存在 `legacy/`；其中“当前”“下一步”只对相应历史
版本有效。通过 [V2 冻结说明](legacy/V2_FREEZE.md) 恢复源码与归档工具，
通过 [来源与许可证](legacy/SOFTWARE_PROVENANCE.md) 查看保留代码的出处。
旧文档原导航见 [历史索引](legacy/README.md)。

构建、实验与大原始记录留在隔离的 hn072 服务器目录；[操作说明](operations/HN072_RESEARCH.md)
记录开发环境。`rtl/` 与 `wafer_simulator` 由独立开发线维护。
