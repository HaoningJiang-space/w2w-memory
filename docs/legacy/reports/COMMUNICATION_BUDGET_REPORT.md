# 冻结 V2：128 B Compute NoC 成本实验

这是 V3 重构期间并行完成的 V2 实验，不是 V3 物理机器的性能结果。
执行源码 d5674f9，离线分析源码 6120344；对应 tags 为
`v2-cost-128-d5674f9` 和 `v2-cost-analysis-6120344`。

固定 c2_b4 四-token 输入、q4 有限行选择、显式 ComputeService、36 个原聚合计算
引擎及原生 RWDL；只将 C–C flit 256 B 改为 128 B，并把输入 credit 槽 16 改为
32，保持每输入 4096 B。NI 64 KiB、本地 DMA payload beat 和 SRAM 写口 256 B/cycle
不变。两项完整层及独立分析均通过，运行期间使用定时检查。

| 组织 | 256 B 参考，μs | 128 B 候选，μs | 完成时间增加 | 吞吐保留 |
|---|---:|---:|---:|---:|
| Gather | 463.263 | 810.166 | 74.8825% | 57.1812% |
| Near-shard | 258.830 | 259.672 | 0.32531% | 99.6757% |

| 资源代理 | 256 B | 128 B |
|---|---:|---:|
| C–C 数据线，bit·mm | 7,274,496 | 3,637,248 |
| C–C 数据 pipeline bits | 3,809,280 | 1,904,640 |
| 每输入 data bytes／cell 槽 | 4096／16 | 4096／32 |
| 64-bit sideband／cell | 保留 | 保留，存储槽增加 |

**执行合同限定：远端每个 cell 单独调用接收写口，短写分别向上取整。**
4 KiB＋16 B envelope 在 256 B cell 下为 17 次写工作，在 128 B cell 下为
33 次，虽然物理接收写口仍为 256 B/cycle。因此本实验同时改变了 remote packing
与排空工作，不是“只有物理网络带宽减半”的隔离测量。
Gather 最忙接收写口服务工作由 234.966 μs 增至 400.950 μs，Near-shard 由
112.788 增至 113.556 μs。本地同一 4 KiB payload 在两边都是 16 次写服务。

结果支持：在这份冻结执行合同下，Near-shard 能在数据线与流水位数减半的
候选中保留大部分性能；不能将 Gather 的全部退化归因于长线吞吐或推出真实 PPA。
只有两个数据位宽、一个 workload/service 点，没有证明通信配置最优。

[精选摘要](../../../artifacts/results/communication_budget/summary.json) 保存控制匹配、
资源和服务工作；[证据包](../../../artifacts/provenance/communication_budget/selected-delivery-evidence.tar.gz)
包含注册、冻结输入、完成记录、离线完整分析和定时日志。
原始 captures 在 `hn072:/Projects/haoning/w2w-full-system-communication-20261009/study`，
参考源码／native 身份由包内 registration 和 V2 freeze 记录恢复。
