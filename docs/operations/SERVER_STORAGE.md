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
本轮保留；后续应按已结束批次核验并归档/迁移，再删除本地展开副本。
`wafer_simulator/downloads/atlahs` 也包含实际 graph/SQLite trace，未当安装缓存删除。

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
