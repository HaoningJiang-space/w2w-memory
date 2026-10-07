# eex005 实验归档

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
