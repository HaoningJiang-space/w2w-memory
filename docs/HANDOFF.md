# W2W Memory-on-Logic 开发交接

2026-10-09：坐标生成机器与有限流式返回已完成同一个四 token / 4-way routed FFN 层。
**当前结果：[几何与流式返回报告](reports/WAFER_MACHINE_CLOSURE_REPORT.md)。**

| 配置 | 完整层时间 |
|---|---:|
| 旧 10 mm / 2-cycle 合成 mesh，整包（已归档） | 1,041.569 μs |
| 坐标生成 14 / 17-cycle mesh，整包 | 1,055.534 μs |
| 相同新机器，有限前缀流式返回 | 1,064.328 μs |

流式提前供数、降低整 descriptor 就绪后的交付尾部，但改变了 native 接纳顺序；
本次整层慢 0.83%。原生峰值必要下界仍覆盖约 83%–84% 的时间。
**下一步仅落实独立 RWDL 服务域**，详见[唯一当前任务](handoff/NEXT_TASK.md)。
高并行 native、Direct HB 和工艺校准尚未完成。

## 单仓库开发与运行

所有仿真工具修改都维护在 `HaoningJiang-space/w2w-memory` 的 `main`：

| 内容 | 入口 |
|---|---|
| 统一任务/事务时间线 | `w2w/system/kernel.py` |
| 物理坐标导出 | `w2w/system/wafer_machine.py` |
| native BookSim 的原始 fork | `rapidchiplet/booksim2`（历史源码不原地打补丁） |
| 优化补丁、native 在线接口、来源 | `third_party/booksim_runtime` |
| 内置运行接口 / 系统适配 | `network/native_booksim` / `network/booksim_backend.py` |
| 原生 DRAM / 有限流式回调 | `service/dram` / `memory/backend.py` |
| 独立构建 | `tools/build_native.py`；[命令和验证](methods/NATIVE_TOOLCHAIN.md) |
| 注册运行 / 分析 | `run_machine_closure` / `analyze_machine_closure` |
| 冻结输入与摘要 | `artifacts/results/system/machine_closure` |
| 构建证据 / 执行证据 | `artifacts/provenance/native_toolchain` / `machine_closure` |

执行源 `a9066bc`，分析源 `1773804`；两项均完成并排空，原始完整事件留在 hn072
`/Projects/haoning/w2w-full-system-closure-20261009/study-a9066bc`。
41 项相关回归通过；另外从干净 Ramulator clone 构建 bridge 后通过 12 项相关检查。
这是独立构建与新增合同的核验，不是第二套网络验收 campaign。

## 历史与协作

[Home / Pair / 4-way 九项结果](reports/B1_RESIDENCY_STUDY_REPORT.md)及
[三种网络条件结果](reports/MOE_LAYER_SYSTEM_REPORT.md)保持原身份和范围；
它们是 HBM2 reference 下的完整 routed FFN 层，历史 read-only/RTL 仍是组件证据。

本地开发，新构建/测试/实验只在 hn072 隔离目录；源码经 Git 同步，不修改运行中的源码。
旧 `eex005` 仅可用于证据迁移与已核验清理。
另一位开发者的 RTL 和 `/Projects/haoning/wafer_simulator` 目录保留。
凭据、原始数据、native 二进制与环境不入 Git。旧交接见[历史](HANDOFF_HISTORY.md)。
