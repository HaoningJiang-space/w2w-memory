# eex005 实验归档

## 2026-10-07：缓存与传输包清理

用户授权清理 `wangziheng@eex005`。先检查账号目录占用与活动进程，再确认目标路径
没有本账号进程的打开文件/cwd/executable 引用。删除可重建的 Tectonic、pip 缓存，
以及本轮已导入 Git 的四个 `finite-*.bundle` 传输文件；Conda 只使用
`clean --tarballs --index-cache --yes`，没有删除包目录、环境或安装的软件。

直接清理文件占用 6,805,557,248 bytes；另外清理 Conda 下载包 338,421,068 bytes
及索引缓存。操作前后观测可用空间由 67.576 增至 75.048 GiB（约 +7.47 GiB）。
服务器另有持续写入/传输，后续复查约 69–70 GiB；不可把瞬时空闲值当稳定额度。

源码、唯一实验结果、所有环境和许可证保留。活动中的 COMSOL 传输目录保留。
清理后 W2W venv 的 numpy/scipy/shapely 导入成功，Conda 26.3.2 可用。
[清理清单](../../artifacts/provenance/eex005_cache_cleanup_20261007.json)包含各目标、
尺寸、验证与完整服务器日志位置。本轮有限任务结果已经独立归档到 Git。

### 第二轮：未使用包与编译缓存

继续检查后，Conda dry-run 标记 127 个未使用包缓存（3,106,811,816 bytes）。
扫描账号内 34,688 个软链接及本账号进程的 cwd/exe/fd/maps，未发现对待删目录的引用；
复核清理计划不变后运行 `conda clean --packages --yes`。环境目录未删除。
另删除无活动引用的 `.nv/ComputeCache`、`.triton/cache`、`.npm/_cacache`，
合计 804,323,328 bytes。操作前后观测约释放 3.748 GiB，两轮约 11.22 GiB。

清理后 W2W 数值依赖导入和 Conda 命令正常。仍有其他写入，最终 `df` 显示 `/home`
可用约 71 GiB，不能将两轮删除量简单加到当前空闲值。
[第二轮完整记录](../../artifacts/provenance/eex005_cache_cleanup_round2_20261007.json)。

仍可进一步整理的候选为 `TA-PPAAS/tmp`（约 6.9 GB）、`wafer_simulator/runs`
（约 22 GB）、`thermal_hbt`（目录总量约 78 GB）。它们含实验输入、结果和复现证据，
第二轮保留；后续应按已结束批次核验并归档/迁移，再删除本地展开副本。
`wafer_simulator/downloads/atlahs` 也包含实际 graph/SQLite trace，未当安装缓存删除。

### 第三轮：按内容去重，退役已结束测试的源码展开副本

继续追查大目录后，区分了三种情况：

- **需要保留的证据**：独有温度场、完整 trace、失败原因、接受结果和配置。
  `thermal_hbt` 结果索引仍引用这些数值场，`wafer_simulator` 的 002/006/M1
  结果也承担不同的对照用途，没有因为目录旧或体积大就删除整组结果。
- **内容相同的副本**：逐字节 SHA-256 核对后，对 56 份副本使用 XFS
  `FIDEDUPERANGE` 去重。涉及约 10.42 GiB 的逻辑范围；文件名、inode、大小、
  修改时间及内容均保持不变。预先验证写时复制，后续修改某个文件不会同时改写另一份。
  所有相关文件事后重新验证 SHA-256。没有用硬链接将独立实验文件绑定为同一个文件。
- **可以退役的展开源码**：删除 `TA-PPAAS/tmp/experiments/ThermoDSE` 下 13 个
  已结束测试的 `checkout` / `source`，保留外层输入、结果、日志、binary 和工具。
  删除前检查工作树、忽略文件、不可达对象、活动引用和外部软链接。
  另有 3 个目录未确认结束状态，保留。

13 份展开源码计约 3.18 GiB，归档为约 68 MiB 的 Git 包和恢复信息，位置为：
`/home/wangziheng/TA-PPAAS/tmp/experiments/ThermoDSE/retired_sources_20261007/`。
每份源码包均在新建 bare repository 中验证恢复及 `git fsck`；子模块的原始浅克隆
边界单独保留。另完整恢复了一份 CUDA checkout 和 HD-MoE 子模块，确认工作树干净。
需要历史源码时可运行（目标路径已存在时会拒绝覆盖）：

```sh
cd /home/wangziheng/TA-PPAAS/tmp/experiments/ThermoDSE/retired_sources_20261007
/home/wangziheng/miniconda3/bin/python restore_checkout.py cuda-full-088881f-iXWz3AWh
```

去重窗口观测可用空间增加 **2.457 GiB**；删除 checkout 的窗口增加 **3.193 GiB**。
不能将 10.42 GiB 的去重逻辑范围直接记为物理释放量：磁盘块可能已共享，服务器也有
其他持续写入。归档另占上述约 68 MiB。最终复查 `/home` 可用 **74.860 GiB**，
`df -h` 显示约 75 GiB / 93% 使用率。W2W numpy/scipy/shapely 导入通过。

没有删除独有结果、环境、许可证或活动传输。部分受保护的 sshd/sd-pam 会话进程
无法读取文件描述符；可读取的本账号进程均未引用目标，具体边界保存在记录中。
[完整记录及源码恢复信息](../../artifacts/provenance/eex005_storage_cleanup_round3_20261007.json)
与[本轮维护脚本](../../artifacts/provenance/eex005_storage_cleanup_round3_scripts_20261007.tar.gz)
一同归档。服务器操作日志位于
`/home/wangziheng/Video/w2w-finite-read-20261007/memory_results/cleanup_round3/`。

## 既有实验结果归档

本轮按照用户清理授权，将 13 个已结束实验目录压缩至：
`/home/wangziheng/Video/w2w-memory/memory_results/archive/`。

每份 tar.gz 均逐文件验证 SHA-256 与原文件一致，并再次核对原文件未发生变化后，
才删除对应展开目录。保留结果、运行日志及全部配置，不涉及其他项目或运行环境。
累计减少 296,971,942 字节（约 283.2 MiB）。
逐文件哈希、压缩包哈希与尺寸见 `artifacts/results/provenance/server_cleanup_manifest.json`。

旧报告中的原始输出路径需要先恢复再读取：

```sh
cd /home/wangziheng/Video/w2w-memory/memory_results
tar -xzf archive/eex005_nonuniform_a418ecf.tar.gz
```

其他实验按清单替换归档名。最新端点实验 `eex005_endpoint_82b1e03` 保留展开目录。
Git 中已归档的实验结果及报告不受这次存储清理影响。
