# Wafer-scale Memory Service Fabric

**开发交接入口：[HANDOFF](docs/HANDOFF.md)** — 当前状态、复现、接口边界与下一任务。

研究目标：在有限接口与连线预算下，联合组织 **memory service interface、reticle
placement 和静态数据布局**，使繁忙 compute 能利用已有 DRAM 服务。
Matching、pooling 和 FIFO 是不同层次的工具，不是独立更换的研究题目。
主贡献是 **wafer-scale memory-service sharing architecture**；静态可配置 shared
egress 是关键机制，RTL 是该机制的功能与局部硬件成本验证。

## 目录与职责

```text
w2w/                       研究代码（Python package）
├── geometry/              Memory-on-Logic 几何、HB overlap 与原始服务包络
├── service/               Reticle / bank 资源、固定字节布局与服务 LP
├── endpoints/             出口合同、完整字执行、有限队列与反压
├── synthesis/             Matching/cycle、sparse pooling、DSE 与 ILP
├── workloads/             公共 activity / demand 场景生成
├── experiments/           实验入口、场景划分、冻结与结果记录
├── analysis/              归档结果分析、独立重算与统计
├── validation/            几何/构造证书、批量资源核对
└── visualization/         论文图与研究图生成

tests/                     单元与回归测试
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

- [逻辑读任务导入与依赖回放：固定 H/plus、公平对照和证据范围](docs/methods/READ_WORKLOAD_REPLAY.md)
- [固定研究范围与三层职责](docs/RESEARCH_SCOPE.md)
- [最新：Configurable Shared Egress，同服务减少重复 FIFO](docs/reports/CONFIGURABLE_SHARED_EGRESS_REPORT.md)
- [固定 H/plus 架构竞争与性能/成本前沿](docs/reports/ARCHITECTURE_COMPETITION_REPORT.md)
- [角色接口、home/k2/k3与原生供给敏感性](docs/reports/ROLE_INTERFACE_REPORT.md)
- [不可变Design、端点契约与统一资源账本](docs/DESIGN_API.md)
- [服务合同改变设计选择：首轮结果](docs/reports/CONTRACT_SELECTION_REPORT.md)
- [地址权限与物理可达性审计](docs/reports/EGRESS_REACHABILITY_REPORT.md)
- [代码层次、依赖方向与新旧入口](docs/CODE_STRUCTURE.md)
- [当前闭环结果：Endpoint → bank → wafer](docs/reports/ENDPOINT_BRIDGE_REPORT.md)
- [该闭环的模型、参数与复现范围](docs/methods/ENDPOINT_BRIDGE_METHOD.md)
- [全部阶段文档索引](docs/README.md)

当前固定 H/plus，利用静态数据组织同时争取运行时共享机会和硬件复用机会。
系统侧补充逻辑读任务导入、冻结地址布局与依赖回放；暂无指定真实 trace，先用合成任务
验证 infra。Home、k2、k3 保留结构对照，duplicated/configurable 保留同服务成本消融。
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
python -m unittest discover -s tests -v
python -m w2w run_endpoint_bridge --output memory_results/endpoint_bridge/results.json
python -m w2w analyze_endpoint_bridge artifacts/results/endpoint/endpoint_bridge_results.json
```

统一入口沿用原脚本名称，也接受 `run_endpoint_bridge.py` 这种名称；完整模块形式
`python -m w2w.experiments.run_endpoint_bridge` 同样可用。旧的根目录命令
`python run_endpoint_bridge.py` 已由上述入口替代，没有保留一批重复 wrapper。
需要干净 Git 提交的实验仍然保留原检查。

只维护 **main**。[Git 同步流程](docs/operations/GIT_WORKFLOW.md)；
[服务器历史实验归档与恢复](docs/operations/SERVER_STORAGE.md)。
代码、报告及选定原始结果在同一 Git 历史中；本次目录迁移未改写历史结果内容。

## Upstream artifact

Based on [spcl/nw-design-for-wsi](https://github.com/spcl/nw-design-for-wsi),
retaining its history and original attribution below.

### Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding

This repository contains the artifacts accompanying the paper:

**“Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding.”**
