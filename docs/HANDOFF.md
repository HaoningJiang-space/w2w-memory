# Wafer scale memory service 开发交接

当前目标是在重复 reticle 的 WoW 系统中，联合组织 DRAM 服务接口、物理连接和静态数据驻留，使空闲服务能够被繁忙 compute 利用。Matching、endpoint 与 RTL 是方法组件。

**当前优先级：[原生服务域与静态驻留联合配置](methods/WAFER_DRAM_SERVICE_PRINCIPLES.md)。** 81次独立请求回放已收齐；结合[研究证据与强基线](RESEARCH_STATUS.md)选择下一项配置，不重复该批实验。

本页只记录当前状态。此前逐轮交接完整保存在 [历史记录](HANDOFF_HISTORY.md)，其中“当前”“下一步”、路径和测试数只适用于各自提交，不作为新开发任务。

本次分层整理通过 62 项相关测试，八个候选和三个对照身份不变；189 份合成归档及
48 份真实回放相关证书重新核对。没有重跑这些性能实验，见[整理验收记录](../artifacts/provenance/provisioning_cleanup/receipt.json)。

## 已完成与尚未完成

| 项目 | 当前状态与入口 |
|---|---|
| 真实输入 | 256 个 Qwen3/MMLU requests，约 849 MB，逐文件身份核对；raw 留服务器 |
| 完整读阶段模拟 | 九窗口、48 次注册回放，1,094,980,608 个 32-byte 字；[结果](reports/PATTERNS_REPLAY_STUDY_REPORT.md) |
| 输入闭环历史验收 | 服务器完整 Python 测试 148/148；48 记录重新解析原始输入与资源审计；[范围](reports/TRACE_FLOW_ACCEPTANCE.md) |
| 静态可配置出口 | 每 bank 一个共享发送结构，方向按 memory 实例冻结；不是跨 bank engine pool |
| 局部物理实现 | Nangate45 单角、提取后 timing 和路由器 DRC；[ASIC 报告](reports/ENDPOINT_ASIC_SLICE_REPORT.md) |
| DRAM 命令时序 | 已接公开 Ramulator HBM2 参考：ACT/PRE/RD/refresh、有限队列与完成回调；8次完整对象回放、193项测试；[结果与边界](reports/DRAM_COMMAND_BRIDGE_REPORT.md) |
| 整片 PPA 与 signoff | 尚未完成；局部面积不能直接当整片面积、功耗或工艺签核 |
| 请求容量与驻留联合配置 | 新比例已完成 189 次合成回放；真实 48 记录仅增加下界，未重跑新比例；[报告](reports/SERVICE_PROVISIONING_REPORT.md) |
| 新比例的独立 routing 验证 | 87主实验＋47目标扩展＋32 RX诊断已完成并审计，共166次；[完整报告](reports/RETURN_PATH_PROVISIONING_REPORT.md) |
| 完整返回路径配置 | RX2使160/192-bit实际率受限；RX3及匹配比例在5个有正参考收益的窗口保留81.82%–83.32%增量，增加RX成本；不是新RTL结果 |
| 静态裁剪强基线 | 六项映射、28项mapped配对回放完成；固定专用更小，可配置以约4% source面积代价保留选择；[结论](RESEARCH_STATUS.md) |
| 新 service-engine pool | 研究提案，未实现；[问题分析与形式化](methods/SERVICE_PROVISIONING_ASSESSMENT.md) |
| cohort静态owner | layer0训练探针在固定硬件上改善评分4.90%–7.77%；非测试集/任务加速；[设计报告](reports/COHORT_SERVICE_DESIGN_REPORT.md) |
| 冻结cohort独立请求回放 | 48新请求、九窗口、81次全部完成，1,815,921,504字；C映射改善2/9、宽k3有负例；[报告](reports/COHORT_REPLAY_REPORT.md) |
| 原生供给匹配驻留 | 同一B接口与HBM2，8/13改1/2，完整单对象时间减少17.44%；[两次诊断](reports/NATIVE_MATCHED_RESIDENCY_REPORT.md) |
| 长路径返回状态 | 48项局部beat周期见证，显式计链路/RX；未改RTL或系统RX3合同；[报告](reports/BEAT_RETURN_CONTRACT_REPORT.md) |

运行基线：真实回放 `aa9d911`；强化审计 `6d1827b`；完整测试与验收记录 `ce549ce`。另已合入 `11fd2ab` 的比例推导、189 次合成回放及独立审计，原执行源码为 `eefe539`。后续文档提交不会改变这些实验的源码身份。GPU 推理不是当前流程的必需步骤。

返回路径CPU实验：准备`23e2711`，87＋47回放`5c425e5`，32 RX诊断`34932c6`，独立审计/图`0fdb4b7`。
共交付3,006,327,648个32-byte字；57项执行相关测试及后续21项定向测试通过（有重叠，非78项唯一测试）。
本轮在eex005隔离worktree执行，hn072核对原始routing；另一开发者的RTL和DRAM后端任务未修改。
旧训练owner的两窗口退化继续保留。共同完成感知映射现已完成新的冻结回放：Home/k2九窗持平，
C两窗改善、七窗持平；宽k3四窗改善、四窗持平、一窗退化。不直接扩跨bank pool。

新81次执行源码`0e66ff7`，eex005，1922.74 s；输入raw在hn072核对。
53项相关测试、4项入口测试通过；结果审计`35c0592`、最终证据整理`a1c9bb3`。
最大资源下界差11槽/0.0173%，后续先检查原生资源域与字节分配。
另一开发者的hn072独立复跑另存`cohort_replay_replica`，不拼入本批完成统计。

最新设计探针`9f647c8`已由`eb1f6a8`独立核对：32次owner交换、24项交叉评分；
在eex005对`4422cc4`的定向检查中42项通过、5项原生桥接集成跳过；这是该隔离环境的检查，
与hn072已归档的193项通过及随后3项归档检查通过分开记录。`b4b8ce6`已包含于祖先链，
并行DRAM代码及原生证据已保留至`6c77303`。模型整字RX预留与RTL beat-reservoir应区分，见新设计报告。

## 工作区和 Git

- 仓库：[HaoningJiang-space/w2w-memory](https://github.com/HaoningJiang-space/w2w-memory)，唯一维护分支 `main`。
- 本地：`/Users/haoning/project/w2w/nw-design-for-wsi`，在这里开发。
- CPU 服务器：`hn072@143.89.78.72:/Projects/haoning/w2w`，通过 Git 拉取后运行。
- 本地 `origin` 保留上游，`research-origin` 指向研究仓库；不改写历史或覆盖他人工作。
- `memory_results` 指向服务器原始 trace/实验目录；`build/asic_runs` 指向既有物理结果。
- HF 默认直连，VPS 隧道停用。凭据、raw trace、环境与临时输出不进 Git。

详细命令见 [服务器运行说明](operations/HN072_RESEARCH.md) 和 [Git 工作流](operations/GIT_WORKFLOW.md)。

## 从哪里接代码

| 职责 | 当前入口 |
|---|---|
| 不可变设计与合同 | `w2w/domain/design.py`、`endpoint.py` |
| 几何与 overlap | `w2w/geometry/memory_model.py` |
| 原始 routing 与读任务 | `w2w/workloads/patterns_download.py`、`patterns_trace.py`、`read_trace.py` |
| 固定地址驻留 | `w2w/workloads/read_residency.py` |
| 请求容量感知候选 | `w2w/synthesis/provisioning_catalog.py`，候选比例由解析界生成 |
| 冻结设计重建 | `w2w/synthesis/read_catalog.py`，不依赖 experiment runner |
| 资源约束与服务 LP | `w2w/service/resources.py`、`solver.py`、`evaluator.py` |
| 有限读执行 | `w2w/service/read_replay.py`；可选 `service/dram` 命令后端，默认仍为 slot 参考 |
| Endpoint 微架构执行 | `w2w/endpoints/endpoint_execution.py`、`role_execution.py` |
| 实验注册 | `w2w/experiments/`；统一入口 `w2w/commands.py` |
| 独立审计 | `w2w/validation/patterns_replay.py` |
| 汇总与绘图 | `w2w/analysis/patterns_replay.py`、`w2w/visualization/render_patterns_replay.py` |
| RTL 与局部物理流程 | `rtl/`、`w2w/experiments/run_endpoint_asic.py` |

完整依赖与历史入口见 [CODE_STRUCTURE](CODE_STRUCTURE.md)。新增模型放公共层，runner 只编排实验；不要把源码、结果、绘图和下载塞进同一个脚本。

## 接手先做什么

先复核已有归档，无需再运行 48 个长回放：

```sh
python -m w2w --list
python -m w2w audit_patterns_replay --source artifacts/results/workload/patterns_replay/flow --output build/patterns_replay_audit
```

服务器对原始输入重编译的命令见 [TRACE_WORKFLOW](guides/TRACE_WORKFLOW.md)。实验参数、冻结布局和旧结果不随目录整理变化。当前回放是 routing 驱动的权重读阶段，不是实测 DRAM traffic 或端到端 LLM latency。

随后按 [NEXT_TASK](handoff/NEXT_TASK.md) 比较同等优化的Home和共享设计，并核实模板复用价值。不要把历史 Gate 的“下一步”重新当成未完成任务。
