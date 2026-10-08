# 代码结构与开发入口

## 当前主流程：真实 routing 到有限读回放

2026-10-07 完成输入闭环后的整理：冻结设计目录不再藏在 `run_read_workload.py` 中，
审计与绘图分层；旧模块入口保留兼容导出。没有改变注册实验、设计顺序或服务语义。

| 阶段 | 可复用模块 | 命令 / 数据 |
|---|---|---|
| 获取与身份验证 | `workloads/patterns_download.py` | `download_patterns_corpus`；原始数据在服务器 `memory_results` |
| routing → distinct experts → 完整权重读任务 | `workloads/patterns_trace.py`、`read_trace.py` | `import_patterns_trace`；执行假设在 `spec.json` |
| 重建冻结硬件/布局 | `synthesis/read_catalog.py` | 检查历史 catalog 的布局身份和成本；不针对请求搜索 |
| 有限 credit、地址驻留、endpoint/HB/RX 执行 | `service/read_replay.py`、`workloads/read_residency.py` | `replay_patterns_window`；逐字与逐槽守恒 |
| 可选 DRAM 命令后端 | `service/dram/ramulator.py`、`bridge.cpp` | `run_dram_bridge` / `audit_dram_bridge`；[范围与构建](methods/DRAM_COMMAND_BRIDGE.md) |
| 注册窗口与 CPU 作业编排 | `experiments/run_patterns_replay_study.py` | 九窗口、48组合；`plan.json` 冻结样本/设计/预算 |
| 输入与结果独立核对 | `validation/patterns_replay.py` | 原始 union、字节、哈希、覆盖、资源必要界 |
| 报告导出 | `analysis/patterns_replay.py` | `audit_patterns_replay` → JSON / CSV |
| 图形 | `visualization/render_patterns_replay.py` | 只消费审计后的记录，不重新求解或下载 |

`analysis` 和 `validation` 不再为读取设计而导入实验 runner。
实验 runner 可以依赖公共目录，公共目录不能反过来启动实验。
历史 `run_read_workload.load_designs`、`analysis.patterns_replay.audit` 仍可导入；
新代码使用各自的 `synthesis` / `validation` 位置。

从仓库根目录执行：

```sh
python -m w2w --list
python -m w2w run_patterns_replay_study --help
python -m w2w audit_patterns_replay --help
# 不需要原始大 trace 的归档复核：
python -m w2w audit_patterns_replay \
  --source artifacts/results/workload/patterns_replay/flow \
  --output build/patterns_replay_audit
```

服务器原始运行目录可再加 `--verify-inputs`，会重新读取授权原始 JSON 并编译核对。
下载、编译、回放、审计均保持独立入口，审计不会触发下载或重跑实验。
[完整工作流与验收范围](guides/TRACE_WORKFLOW.md)。
下载器的 HTTP、授权边界、文件身份与已完成文件恢复逻辑也已移至 `workloads`；
`fetch_patterns_sample` 只保留 CLI 和历史导入兼容。单样本 CLI 默认官方 HF 原站，
镜像需显式 `--endpoint`，不会自动转站。没有新增部分文件 Range 恢复行为。
[结果与完整命令](reports/PATTERNS_REPLAY_STUDY_REPORT.md) / [服务器工作流](operations/HN072_RESEARCH.md)。

## 研究证据与强基线

`analysis/research_evidence.py`重建既有性能/成本对照，未知PPA不补零。`rtl/baselines/endpoint_fixed_source.sv`只做综合前静态特化；`experiments/run_static_binding_baseline.py`执行同库映射与配对回放；`validation/static_binding.py`重建原始stat和日志。三者职责分离，不修改主执行器、冻结候选或旧结果。

## 既有模型层次

2026-10-07 新增不可变设计与契约边界，详见 [Design API](DESIGN_API.md)。
固定字节 LP 已迁至 `service/solver.py`，旧入口为兼容导出；端点容量通过
`EndpointEnvelope` 交给共享 `ResourceLedger`，不再继承 service。

本次是目录与公共依赖整理，不改变服务公式、实验 seeds、优化目标或硬件参数。
旧结果及摘要按字节原样迁移；路径清单和 SHA-256 在
[迁移记录](../artifacts/provenance/layout_migration.json)。历史提交仍可复现旧命令。

## 分层职责

| 目录 | 应放什么 | 主要模块 |
|---|---|---|
| `w2w/domain` | 不可变设计、endpoint 参数与服务包络，不依赖求解器或实验 | `design`、`endpoint` |
| `w2w/theory` | 解析必要界与纯数学推导 | `interfaces`、`service_provisioning`、`cohort_service` |
| `w2w/geometry` | Memory-on-Logic 的几何生成、HB overlap、初始服务包络 | `memory_model` |
| `w2w/service` | 资源账本、固定数据布局、reticle/bank 服务 LP | `matching_placement`、`bank_sharing`、`guaranteed_service_exchange` |
| `w2w/endpoints` | 出口服务合同、完整字执行、队列与反压 | `endpoint_contract_probe`、`endpoint_execution`、`slice_exposure_probe` |
| `w2w/synthesis` | 选择布局或硬件的算法 | `cycle_configurations`、`sparse_pooling`、`service_driven_fabric`、`nonuniform_pooling`、`gurobi_pair_synthesis`、`memory_fabric_dse`、`cohort_placement` |
| `w2w/workloads` | 活动集合、真实 routing、逻辑读任务和冻结地址驻留 | `bank`、`reticle`、`patterns_trace`、`read_trace`、`read_residency` |
| `w2w/experiments` | 注册参数、train/val/test、冻结、执行和记录 | `run_*` |
| `w2w/analysis` | 读取结果、独立重算、统计 | `analyze_*` |
| `w2w/validation` | 构造证书、守恒检查、资源复核 | `verify_*`、`resources` |
| `w2w/visualization` | 生成图形 | `plot_*`、`render_*`、`draw_*` |

共享参数在 `w2w/constants.py`；环境记录在 `w2w/provenance.py`；归档路径在
`w2w/paths.py`。包导入不会启动实验或生成图片。

旧模型中少量 baseline 构造和布局辅助函数仍与其服务模型放在一起，以保持 API
及历史行为。这次没有趁搬目录重写算法。上游几何和 NoC 工具仍位于根目录：
研究代码通过显式 import 使用它们，保留原工具运行方式和第三方依赖结构。

## 依赖方向

```text
upstream geometry + constants + workloads
                    ↓
              geometry / service
                    ↓
          endpoints / synthesis
                    ↓
     experiments / analysis / validation
                    ↓
                 artifacts
```

公共 workload 和 provenance 不再从 `run_*.py` 导入。模型与综合算法不要依赖实验
入口；实验负责调用模型、记录参数和冻结结果。`validation/resources.py` 复用综合
层的独立原始资源核对，不参与算法选方案。

## 历史 endpoint 闭环入口

1. [EndpointFixedService / 完整字执行](../w2w/endpoints/endpoint_execution.py)
2. [ExposureFabric / FixedService](../w2w/service/guaranteed_service_exchange.py)
3. [冻结的 endpoint-to-wafer 实验](../w2w/experiments/run_endpoint_bridge.py)
4. [独立配对复核](../w2w/analysis/analyze_endpoint_bridge.py)
5. [执行与接入测试](../tests/test_endpoint_execution.py)

## 统一命令

在仓库根目录：

```sh
python -m w2w --list
python -m w2w run_endpoint_bridge --help
python -m w2w run_endpoint_bridge --output memory_results/my_endpoint/results.json
python -m w2w analyze_endpoint_bridge artifacts/results/endpoint/endpoint_bridge_results.json
python -m unittest discover -s tests -v
```

入口保留原脚本 stem，甚至接受 `.py` 后缀：
`python -m w2w run_endpoint_bridge.py ...`。也可以直接用完整模块路径。

| 原入口 | 当前入口 |
|---|---|
| `python run_endpoint_bridge.py ...` | `python -m w2w run_endpoint_bridge ...` |
| `python endpoint_contract_probe.py ...` | `python -m w2w endpoint_contract_probe ...` |
| `python analyze_nonuniform_pooling.py ...` | `python -m w2w analyze_nonuniform_pooling ...` |
| `python -m unittest test_endpoint_execution` | `python -m unittest tests.test_endpoint_execution` |
| `from guaranteed_service_exchange import FixedService` | `from w2w.service.guaranteed_service_exchange import FixedService` |

没有保留根目录 wrapper 或全局 `sys.path` 注入；旧直接文件命令需要按表更新。
文档中已更新可运行命令。原脚本的参数保持原语义；有些分析/绘图脚本不提供
`--help`，用统一 `--list` 查找入口，再看对应模块或方法文档。

## 结果、报告与服务器

- `docs/methods`：实验协议；`docs/reports`：结果；`docs/theory`：推导。
- `docs/background`：物理证据/related work；`docs/operations`：Git 与服务器。
- `artifacts/results/<stage>`：精选原始结果、摘要、证书。不要修改旧结果去匹配新模型。
- `artifacts/figures/<stage>`：SVG 正式图；PNG 仅作本地预览。
- `memory_results/<run>`：新运行的工作目录，保持原位置，避免破坏服务器归档恢复。
- 上游 `results/` 和 `plots/` 不是本研究新结果目录，保留原样。

新研究代码应进入对应层；新增实验注册在 `w2w/commands.py`。仍只使用 `main`，
通过 Git 同步到当前 CPU 服务器 `/Projects/haoning/w2w`；eex005 保留历史实验。
需要干净提交的 runner 保留原检查，不为重构绕过检查。

## 后续扩展的边界

合入 `11fd2ab` 的 service provisioning 工作后，注册候选构造由实验 runner 移至
`synthesis/provisioning_catalog.py`；原 `run_service_provisioning.candidate_designs`
继续兼容导入。八个设计、三个 duplicated 对照、比例推导和 catalog 身份保持不变。
`analysis/service_provisioning.py` 计算资源必要界，`validation/service_provisioning.py`
复核归档，`visualization/render_service_provisioning.py` 绘图；runner 只负责注册与执行。
纯容量/请求生命周期公式移至 `theory/service_provisioning.py`，旧 analysis 导入保留兼容；
候选构造和绘图直接依赖 theory，不通过归档分析层调用这些公式。

当前 `EndpointSpec.shared_fifo_ports` 是 **bank-local** 共享状态；
`MemoryFabricDesign.shared_directions` 是每 memory 实例的冻结方向。
它们不表示跨 bank 的 engine pool。新增 pool 必须显式表示 bank-engine 支持、
静态 binding、并发容量和互连成本，不能仅更改旧字段名称。

当前 native ready pattern 和读 slot 也不表示 ACT/PRE/RD/refresh。
命令时序后端已在 `service/dram` 实现，通过接受、推进、完成接口与读执行器交互；
公开HBM2参考与旧slot具有不同原生服务预算。旧 slot 模型继续用于历史复现。

服务配置提案见 [分析与形式化](methods/SERVICE_PROVISIONING_ASSESSMENT.md)。
当前交接只看 [HANDOFF](HANDOFF.md) 与 [NEXT_TASK](handoff/NEXT_TASK.md)；
逐轮状态已另存历史页，避免旧“下一步”与当前任务相互冲突。

`analysis/template_binding.py`检查固定出口的均匀方向限制与条件旋转构造，输出几何/字节份额证据；不修改几何生产模型或endpoint执行器。制造未知项保留在报告中。

## 冻结cohort回放与原生供给诊断

| 职责 | 入口 |
|---|---|
| 固定请求划分、owner身份和逻辑任务 | `workloads/cohort_replay.py` |
| 固定Home/k2/wide/C及同服务duplicated | `synthesis/cohort_replay.py` |
| 导入与81次有限读回放 | `prepare_cohort_replay`、`run_cohort_replay` |
| 原始输入重编译、独立结果核验 | `audit_cohort_replay` |
| 逐窗口配对统计与图 | `analyze_cohort_replay`、`render_cohort_replay` |
| 局部beat周期与完整payload计数 | `theory/beat_return.py`、`probe_beat_return` |
| 已归档原生容量、延迟与在途必要界 | `analyze_dram_service_limits` |
| 同一原生profile的两种静态比例 | `probe_native_residency`、`audit_native_residency` |

这些入口均经`python -m w2w`调用。分析和核验不触发训练或长回放；
beat计数合同、旧slot任务时间和HBM2命令结果分别保存，不覆盖历史执行语义。
