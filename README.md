# W2W Memory-on-Logic

研究空间分布的原生 DRAM 服务，如何与跨晶粒通信、有限 SRAM 和计算放置配平。
当前系统执行真实 routing 的一个完整 gated FFN 层，复用 native BookSim 与
Ramulator 的路由/credit、原生命令/刷新框架；这是时序模型，不是完整 LLM 或数值推理验证。

[当前交接与下一任务](docs/HANDOFF.md) · [代码职责](docs/CODE_STRUCTURE.md) ·
[全部阶段文档索引](docs/README.md)

当前[完整层结果](docs/reports/COMPUTE_LOCALITY_SERVICE_BALANCE_REPORT.md)：四条计算链匹配后，
远端执行307.813 μs，就近执行258.825 μs，减少15.915%。明确供数预算与有限行选择
controller下，集中/就近为463.263/258.830 μs，减少44.129%；简单轮转的负结果也保留。
[上一阶段45.21%](docs/reports/RWDL_COMPUTE_PLACEMENT_REPORT.md)同时改变布局与并行结构。
当前入口复用固定routing、36个共享引擎，分开声明RWDL接口、阵列时序、controller、
汇聚和计算SRAM服务。[原生合同](docs/methods/RWDL_NATIVE_SERVICE.md)区分接口峰值、
行/刷新约束与实际返回路径。机器是未标定候选，计算bank/内部汇聚与预约协议尚未
物理闭合，资源代理不代表真实PPA。

已冻结的 [HBM2 驻留结果](docs/reports/B1_RESIDENCY_STUDY_REPORT.md) 和
[几何／整包／流式报告](docs/reports/WAFER_MACHINE_CLOSURE_REPORT.md) 保持原身份。
历史 LP、read replay 和 endpoint RTL 保留复现入口，从完整索引进入。

## 开发与运行

源码本地编辑，保持 `main`；构建、测试、实验只在 `hn072@143.89.78.72` 的
`/Projects/haoning/w2w-full-system-*` 隔离目录。通过 Git 同步冻结源码，运行时不更新。
不修改其他开发者的 RTL 或 `wafer_simulator` 工作区。

```sh
python -m w2w --help
python -m w2w --list --scope current
python -m w2w --list --scope reference
python tools/build_native.py --help
python -m w2w run_compute_placement --help
python -m w2w analyze_compute_placement --help
```

依赖见 `requirements-memory.txt`；[统一 native 构建](docs/methods/NATIVE_TOOLCHAIN.md)
从本仓库补丁/runtime 与锁定 Ramulator 构建到外部目录。原始事件、二进制、环境、
凭据不入 Git。[服务器流程](docs/operations/HN072_RESEARCH.md) 与
[Git 同步](docs/operations/GIT_WORKFLOW.md) 给出复现约束。

命令继续惰性加载，旧名称与 `.py` 后缀可用。默认帮助突出 Current；完整列表按
Current / Reference / Legacy 分组。新实验直接使用公共 I/O、两种历史指纹、Git
身份与纯摘要，不从另一个 runner 借实现。

## 执行链

```text
machine + workloads → experiments → system.kernel
                                      ├── memory + service/dram
                                      └── network + 本地 DMA / SRAM
                          events → analysis / validation
```

`w2w/machine/` 定义机器与坐标，`workloads/` 选择 routing 并编译任务；
`system/` 维护统一时间和资源生命周期。native 源码/补丁布局和原始上游目录保留。
本地 DMA 和共享接收写口已独立提取；结构整理保持原语义，模型修正另行提交。

## Upstream artifact

Based on [spcl/nw-design-for-wsi](https://github.com/spcl/nw-design-for-wsi),
retaining its history and original attribution below.

### Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding

This repository contains the artifacts accompanying the paper:

**“Network Design for Wafer-Scale Systems with Wafer-on-Wafer Hybrid Bonding.”**
