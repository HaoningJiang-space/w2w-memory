# 单仓库仿真工具链

2026-10-09。系统源码、物理机器生成、网络适配、BookSim 优化与在线接口、DRAM bridge、
实验入口和构建脚本均由 `HaoningJiang-space/w2w-memory` 管理。
新系统默认不再读取另一个开发者的 `wafer_simulator` 工作区。

| 组成 | 本仓库位置 | 构建输入 |
|---|---|---|
| 系统、机器、任务与内存事务 | `w2w/system`、`domain`、`memory`、`workloads` | 本仓库 commit |
| 优化版 BookSim 基础源码 | `rapidchiplet/booksim2` | 保留原始 fork 和许可证 |
| 已选优化、供数/提交 hook | `third_party/booksim_runtime/*.patch`、`native/` | 原始复制来自 `wafer_simulator@0c56c24`，逐文件来源见 manifest |
| 持久进程和配置接口 | `w2w/network/native_booksim` | 导入路径改为本地；配置生成保持原有参数 |
| DRAM 薄适配与扩展 | `w2w/service/dram`、`w2w/memory/backend.py` | Ramulator 原始版本锁定 `72427a1` |
| 统一构建入口 | `tools/build_native.py` | 新建隔离输出；保存命令、版本及哈希 |

原始 Ramulator 作为未修改的上游依赖获取；所有 W2W 修改都在本仓库。BookSim 的
143 个原始文件已经在 Git 中，构建复制后应用补丁，不修改历史 fork。原始许可证和
JSON 的 MIT notice 保留。运行不需要另一套 Python 系统调度器。

## 在 hn072 构建

以下使用已安装 Python 环境（需要 PyYAML、项目 Python 依赖）、CMake、g++、make、
flex/bison。只通过 Git 同步已提交源码；输出目录必须尚不存在且位于源码树外。

```sh
cd /Projects/haoning/w2w-full-system-closure-20261009/source
/Projects/haoning/w2w/.venv/bin/python tools/build_native.py \
  --output /Projects/haoning/w2w-full-system-closure-20261009/native-NEW \
  --ramulator-source /Projects/haoning/w2w-tools/ramulator2-72427a1
```

不传 `--ramulator-source` 时，脚本在输出目录 clone 指定上游并构建，然后编译本仓库
bridge。这个模式仍需要获取第三方原始依赖，不能称为离线构建。若只需 BookSim，
使用 `--tool booksim`；它的全部源码和 JSON header 已在本仓库，无需外部 checkout。

输出 `build-manifest.json` 记录真实路径和 SHA256，`build.log` 保存构建日志。失败会
保留诊断文件并不标记完成。脚本拒绝覆盖已有输出，重试请使用新目录。

## 运行

设置 `W2W_BOOKSIM_BINARY` 为新生成的 `booksim/endpoint_booksim`；设置
`W2W_RAMULATOR_BRIDGE` 为输出中的实际 ABI 扩展文件，`PYTHONPATH` 加入原始
Ramulator 的 `python` 目录。**不要设置 `W2W_BOOKSIM_SOURCE`**，新默认使用内置接口。
`run_moe_layer` 也不再要求 `--booksim-source`。

显式 `--booksim-source` 仍支持固定旧版本，仅用于历史复现。它不决定新主线的
源码归属。后续 native 修改直接提交本仓库，重建后使用新的二进制身份，不覆盖
旧报告中的执行文件、结果或 source hashes。
