# Wafer-scale Memory Service Fabric

**当前结果：[Home / Pair / 4-way 的完整 routed FFN 层比较](docs/reports/B1_RESIDENCY_STUDY_REPORT.md)。**
两个单 token 与预定四 token batch 中，4-way 相对 Pair 的层时间分别缩短
49.00%、23.07%、38.96%；两单 token 的 Pair 均比同 owner Home 慢约 3.11%。
这些结果属于 36-channel HBM2 reference＋合成 stitched mesh、整 descriptor 返回。
**物理 wafer 尚未校准**；下一步按[机器与返回边界合同](docs/methods/WAFER_MACHINE_CLOSURE.md)
连接几何、原生服务、HB 与 NoC，不继续扩大驻留 DSE 或预设 Direct HB 必需。

**开发入口：[HANDOFF](docs/HANDOFF.md)** — 当前状态、复现、接口边界与唯一下一任务。
[执行合同](docs/methods/MOE_LAYER_SYSTEM.md)明确机器、地址、缓冲和时钟；
当前是一个 routed FFN 层的时序模型，不是完整 LLM 或数值推理验证。
新构建、测试、实验只在 `hn072@143.89.78.72` 的隔离目录运行，源码通过 `main` 同步。

**仿真工具统一在本仓库维护。** 优化版 BookSim 的源码补丁、在线 native 接口、
Python runtime 与 DRAM bridge 均已收齐；[统一构建入口](docs/methods/NATIVE_TOOLCHAIN.md)
已在 hn072 独立重建验证。新运行不依赖另一个开发者的 `wafer_simulator` 工作目录。

研究问题：在已有完整 compute NoC 的 Memory-on-Logic 系统上，远端 DRAM 服务
是否需要额外直接路径，以及怎样联合配置原生供给、有限请求容量与静态驻留。
现有 DRAM 桥、固定字节语义和 endpoint RTL 是可复用组件；系统结果决定架构取舍。
历史 [读阶段回放](docs/guides/TRACE_WORKFLOW.md)、[局部 ASIC](docs/reports/ENDPOINT_ASIC_SLICE_REPORT.md)
保留原范围，不自动合并为新系统性能或成本。

## 目录与职责

```text
w2w/                       研究代码（Python package）
├── domain/                不可变系统、物理路径、任务和事务定义
├── system/                唯一执行时间线、任务与资源生命周期
├── network/               native BookSim 适配；Python 小系统参考
├── memory/                地址、MC 与现有 DRAM 后端适配
├── geometry/              Memory-on-Logic 几何、HB overlap 与原始服务包络
├── service/               Reticle / bank 资源、服务 LP、有限逻辑读执行
├── endpoints/             出口合同、完整字执行、有限队列与反压
├── synthesis/             Matching/cycle、sparse pooling、DSE 与 ILP
├── workloads/             下载与身份验证、routing/demand、读任务与静态驻留
├── experiments/           实验入口、场景划分、冻结与结果记录
├── analysis/              归档结果分析、独立重算与统计
├── validation/            几何/构造证书、批量资源核对
└── visualization/         论文图与研究图生成

tests/                     单元与回归测试
third_party/booksim_runtime/ 优化补丁、native 在线接口、来源与许可证
tools/build_native.py       从本仓库构建 BookSim 和锁定版 DRAM bridge
docs/                      方法、报告、理论、背景及运行说明
artifacts/results/         按研究阶段归档的结果与摘要
artifacts/figures/         版本化 SVG；PNG 预览不入 Git
artifacts/provenance/       迁移清单与归档字节校验
memory_results/            本地/服务器实验工作目录（不入 Git）
```

上游 `Reticle.py`、`Wafer.py`、`System.py`、`VerticalConnector.py` 及原始 NoC
脚本仍在根目录；`rapidchiplet/`、`Orion3/`、上游 `results/` 和 `plots/` 保留原结构。
研究扩展统一放在 `w2w/`，不再往根目录增加 Gate 脚本和结果文件。

## 从这里开始

- [当前：Home / Pair / 4-way，固定驻留与完整层结果](docs/reports/B1_RESIDENCY_STUDY_REPORT.md)
- [下一步：Wafer machine 定义、DRAM–HB 边界与有限流式返回](docs/methods/WAFER_MACHINE_CLOSURE.md)

- [前轮：完整层六项网络条件结果与反馈](docs/reports/MOE_LAYER_SYSTEM_REPORT.md)
- [当前完整层执行合同与机器参数](docs/methods/MOE_LAYER_SYSTEM.md)
- [81次独立请求回放：冻结cohort映射、完整资源下界与负例](docs/reports/COHORT_REPLAY_REPORT.md)
- [从wafer模板和DRAM原生服务出发的设计原则](docs/methods/WAFER_DRAM_SERVICE_PRINCIPLES.md)
- [同一原生组织下调整静态比例：完整对象读时间减少17.44%](docs/reports/NATIVE_MATCHED_RESIDENCY_REPORT.md)
- [历史读子系统：完整返回路径配置、166次回放与位宽/RX成本选择](docs/reports/RETURN_PATH_PROVISIONING_REPORT.md)
- [静态驻留与请求容量联合设计：解析比例、189回放和服务硬件取舍](docs/reports/SERVICE_PROVISIONING_REPORT.md)
- [历史读子系统：真实 trace 工作流、主入口与验收范围](docs/guides/TRACE_WORKFLOW.md)
- [48 次多窗口完整回放：全部结果、供给控制和成本](docs/reports/PATTERNS_REPLAY_STUDY_REPORT.md)
- [服务器：本地开发 → Git → CPU 实验](docs/operations/HN072_RESEARCH.md)
- [逻辑读任务导入与依赖回放：固定 H/plus、公平对照和证据范围](docs/methods/READ_WORKLOAD_REPLAY.md)
- [读任务 infra 验收：44 测试、七个冻结设计和两组同服务消融](docs/reports/READ_WORKLOAD_INFRA_REPORT.md)
- [固定研究范围与三层职责](docs/RESEARCH_SCOPE.md)
- [机制：Configurable Shared Egress，同服务减少重复 FIFO](docs/reports/CONFIGURABLE_SHARED_EGRESS_REPORT.md)
- [固定 H/plus 架构竞争与性能/成本前沿](docs/reports/ARCHITECTURE_COMPETITION_REPORT.md)
- [角色接口、home/k2/k3与原生供给敏感性](docs/reports/ROLE_INTERFACE_REPORT.md)
- [不可变Design、端点契约与统一资源账本](docs/DESIGN_API.md)
- [服务合同改变设计选择：首轮结果](docs/reports/CONTRACT_SELECTION_REPORT.md)
- [地址权限与物理可达性审计](docs/reports/EGRESS_REACHABILITY_REPORT.md)
- [代码层次、依赖方向与新旧入口](docs/CODE_STRUCTURE.md)
- [早期闭环结果：Endpoint → bank → wafer](docs/reports/ENDPOINT_BRIDGE_REPORT.md)
- [该闭环的模型、参数与复现范围](docs/methods/ENDPOINT_BRIDGE_METHOD.md)
- [全部阶段文档索引](docs/README.md)

历史 v1 固定 H/plus，利用静态数据组织研究运行时共享机会和硬件复用机会。
该读子系统已接通真实 routing 导入、专家 union、完整权重读任务、冻结地址布局与依赖回放。
合成任务保留为机制测试。Home、k2、k3 保留结构对照，duplicated/configurable 保留同服务成本消融。
Matching、布局与执行模型服务于这项架构验证；暂不扩新优化框架。
当前[source-side TX→HB→RX最小闭环](docs/reports/ENDPOINT_ROUNDTRIP_REPORT.md)
已通过完整字、背压和吞吐对照；新增握手与RX存储均计费。
同库、同约束的[单 slice ASIC 物理验证](docs/reports/ENDPOINT_ASIC_SLICE_REPORT.md)
已完成：修复后 source 面积减少 30.3%，计入相同三个 RX 后减少 14.5%；
Home RX 完整字特化同时用于两种架构。结果限定于局部典型角面积/时序，不含功耗或 wafer/HB 长线。

## 运行

从仓库根目录执行（已有 `.venv` 可直接复用）：

```sh
python -m pip install -r requirements-memory.txt
python -m w2w --list
python -m unittest tests.test_patterns_replay tests.test_patterns_trace tests.test_patterns_batch tests.test_request_window tests.test_read_workload tests.test_repository_layout
# 只复核已归档结果，不下载、不启动长回放：
python -m w2w audit_patterns_replay \
  --source artifacts/results/workload/patterns_replay/flow \
  --output build/patterns_replay_audit
```

统一入口沿用原脚本名称，也接受 `run_endpoint_bridge.py` 这种名称；完整模块形式
`python -m w2w.experiments.run_endpoint_bridge` 同样可用。旧的根目录命令
`python run_endpoint_bridge.py` 已由上述入口替代，没有保留一批重复 wrapper。
需要干净 Git 提交的实验仍然保留原检查。
服务器含原始 JSON 的核对、完整重跑和历史入口区别见[工作流](docs/guides/TRACE_WORKFLOW.md)。
完整 Python 测试可用 `python -m unittest discover -s tests -v`；上面的 65 项是当前输入/回放链的定向验收范围。

只维护 **main**。[Git 同步流程](docs/operations/GIT_WORKFLOW.md)；
[服务器历史实验归档与恢复](docs/operations/SERVER_STORAGE.md)。
代码、报告及选定原始结果在同一 Git 历史中；本次目录迁移未改写历史结果内容。

## Upstream artifact

Based on [spcl/nw-design-for-wsi](https://github.com/spcl/nw-design-for-wsi),
retaining its history and original attribution below.

### Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding

This repository contains the artifacts accompanying the paper:

**“Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding.”**
