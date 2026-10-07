# Wafer-scale Memory Service Fabric

研究目标：在有限接口与连线预算下，联合组织 **memory service interface、reticle
placement 和静态数据布局**，使繁忙 compute 能利用已有 DRAM 服务。
Matching、pooling 和 FIFO 是不同层次的工具，不是独立更换的研究题目。

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

- [固定研究范围与三层职责](docs/RESEARCH_SCOPE.md)
- [代码层次、依赖方向与新旧入口](docs/CODE_STRUCTURE.md)
- [当前闭环结果：Endpoint → bank → wafer](docs/reports/ENDPOINT_BRIDGE_REPORT.md)
- [该闭环的模型、参数与复现范围](docs/methods/ENDPOINT_BRIDGE_METHOD.md)
- [全部阶段文档索引](docs/README.md)

当前闭环固定 H/plus 配对和数据布局，比较出口约束及有限缓冲执行。它是一个
受限配对模型的组合验证，尚不是通用全 wafer 队列模拟或校准后的 DRAM/PPA。

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
