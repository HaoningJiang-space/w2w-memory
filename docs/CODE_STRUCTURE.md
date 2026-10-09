# 当前代码结构与依赖

当前执行链：机器＋已选 routing/owner＋静态驻留 → 实验组装 →
`SystemExecution` → 原生 DRAM / NoC / 本地搬运与 SRAM → 事件 → 分析与核验。
本页描述当前职责；冻结研究报告仍在原路径，通过 [文档索引](README.md) 进入。

## 主线模块

| 位置 | 职责与入口 |
|---|---|
| `w2w/domain/` | 机器、任务、对象、事务与路径的数据结构 |
| `w2w/machine/presets.py` | 固定资源机器；修改 SRAM、链路、窗口不需要改 MoE 编译器 |
| `w2w/machine/geometry.py` | 坐标、线长、data/credit 延迟与资源代理；面积密度仍未标定 |
| `w2w/workloads/routing_input.py` | 显式选择冻结 routing、owner 和 cohort，核对输入身份 |
| `w2w/workloads/moe_task_graph.py` | `compile_routed_layer(routing, residency=...)`，纯任务图编译 |
| `w2w/workloads/moe_partition.py` | 固定四节点组的 intermediate 分块、共享原有计算引擎与归约 |
| `w2w/system/kernel.py` | 唯一时间协调者；依赖、事务、MC/outstanding/SRAM 生命周期 |
| `w2w/system/builder.py` | 机器、地址布局与合法路径核验 |
| `w2w/memory/` | 固定地址、原生服务及就绪事件；不决定专家位置 |
| `w2w/service/dram/` | **当前执行组件**：Ramulator bridge、HBM2 与独立 RWDL 扩展 |
| `w2w/network/booksim_backend.py` | BookSim 供数/注入/接收/commit；本地 DMA 和写口尚在适配器内 |
| `w2w/experiments/` | 选择配置、组装、冻结、执行与保存；不向其他 runner 借公共函数 |
| `w2w/analysis/` | 已完成记录的统计；`system_summary.py` 是无执行副作用的公共摘要 |
| `w2w/validation/` | 事件、字节、资源守恒与已有证据核验 |
| `w2w/common/` | 少量纯 I/O、整数校验、指纹；不引入实验或执行依赖 |
| `w2w/provenance.py` | 轻量 `revision()` 与完整环境记录分别调用 |

`compile_layer()`、`moe_task_graph.machine`、`system.wafer_machine` 以及旧位置的
公共函数保留兼容导出；当前 runner 直接依赖公共模块与机器层。
两种历史 digest 保持不同编码：`digest_system_v2` 使用原 JSON 空白与 NaN 规则；
`digest_read_v1` 使用紧凑编码并拒绝 NaN。不得替换后回写历史身份。

## 依赖边界

实验入口依赖 machine、workloads、system、analysis/common/provenance。
workloads 消费 routing/owner/residency，不构建 native 组件；机器层不选择 token。
执行层不读某份历史实验来决定工作负载。native 适配不依赖 workload 的校验函数。
摘要函数不导入 runner、不启动执行、不选择隐藏输入目录。

统一 kernel 保留；每个资源只有一个状态所有者。后续可以按原语义提取
LocalDma 与共享接收写口，不能同时修改 streaming、仲裁、时钟或服务模型。
MC、requester、NI、SRAM 写口是不同资源，不归并为万能 manager。

## 命令身份

```sh
python -m w2w --help                      # Current 默认导航
python -m w2w --list                      # 完整 Current / Reference / Legacy
python -m w2w --list --scope reference
python -m w2w --list --scope legacy
```

状态与执行 scope 在 `commands.py` 显式登记，模块继续惰性加载；旧命令名、`.py`
后缀和完整模块入口保持可用。Current 为 RWDL、计算放置与系统小样例；Reference
为已冻结的完整层、驻留和几何/返回对照。Legacy 为旧读回放、LP/matching 与 endpoint
研究入口；不删除其复现能力，也不把 read-only/RTL 结果提升为完整层结果。
Python 小网络、IdealBanks、整包返回仍是参考组件，不能替代正式 native 后端。

## native 构建与证据

`rapidchiplet/booksim2/`、`third_party/booksim_runtime/`、
`w2w/network/native_booksim/` 与 `tools/build_native.py` 保持现有构建布局。
[构建合同](methods/NATIVE_TOOLCHAIN.md)；上游 pin、补丁与许可证保留。
`service/` 含多代研究，不能整体归为 legacy 或整体搬迁。

源码本地编辑，通过 Git 同步；构建、测试与实验只在 hn072 的隔离目录。
运行中的源码与输入不更新。选定配置、摘要、日志身份进入 Git；原始事件、native
二进制、环境与凭据不进入 Git。不因改目录重跑九项架构矩阵。

[README](../README.md) 负责项目与运行入口；[HANDOFF](HANDOFF.md) 负责当前状态与
下一任务。本页不追加研究时间线。结构整理、模型修改、架构实验分别提交。
