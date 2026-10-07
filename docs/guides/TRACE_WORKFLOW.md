# 真实 trace 到读阶段模拟：当前工作流

本流程已在 `hn072@143.89.78.72:/Projects/haoning/w2w` 完成 CPU 执行。
当前覆盖真实 routing 导入与固定模型下的读阶段，不包含神经网络执行、实测 DRAM traffic、
完整推理时延或 wafer 物理签核。[48 回放结果](../reports/PATTERNS_REPLAY_STUDY_REPORT.md)。

## 数据经过哪些层

```text
HF 原始 request JSON（固定 revision、大小与哈希）
  → request / decode step / layer / serving cohort
  → distinct-expert union + 固定 expert owner
  → 完整逻辑权重读任务（全部 experts 静态容量）
  → 冻结 bank residency + 已归档硬件目录
  → request credit / native bank / endpoint / HB / RX
  → 交付字数、任务完成、资源与成本记录
  → 原始输入重编译 + 结果审计 → JSON / CSV / 图
```

只有第一层 expert selection 来自真实记录。冷读、批内复用、权重尺寸、owner、驻留、
时序由显式 execution spec 和硬件模型确定，没有把 token 数直接乘完整专家权重。
原始 JSON 不入 Git；代码、协议、manifest、逻辑 trace 和回放证据进入 Git。

## 先检查现有流程，不重复下载或长回放

本地从仓库根目录执行：

```sh
.venv/bin/python -m w2w audit_patterns_replay \
  --source artifacts/results/workload/patterns_replay/flow \
  --output build/archive_audit
```

这核对全部 48 组归档，没有原始 JSON 时不加 `--verify-inputs`。
服务器保存着完整的原始 corpus，可以核对更早的输入层：

```sh
cd /Projects/haoning/w2w
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w audit_patterns_replay \
  --source memory_results/pbc_multiwindow --verify-inputs \
  --output build/raw_input_audit
```

期望摘要为 `replay_count=48`、`cases=9`、`delivered_words=1094980608`；
服务器原始核对还应为 `raw_input_recompiled=true`。这是核对历史结果，不产生新性能数据。

## 需要新的运行时

继续本地开发、提交并 push `HaoningJiang-space/w2w-memory` 的唯一 `main`；
服务器拉取后，从干净提交启动，使用新的输出目录：

```sh
cd /Projects/haoning/w2w
git pull --ff-only research-origin main
git status --short
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w run_patterns_replay_study \
  --manifest memory_results/pbc_corpus256/manifest.json \
  --output memory_results/pbc_replay_new
```

默认读取已经冻结的 `artifacts/provenance/patterns_replay/plan.json`。
若要改变 requests、窗口、设计或预算，另行注册新协议并提交；不能修改旧归档冒充复现。
运行完再对新目录执行 `audit_patterns_replay --verify-inputs`，审计失败则不报告完成。
本轮原始执行提交为 `aa9d911`，后续代码整理不改写这个来源。

## 入口如何选择

| 命令 | 用途 / 范围 |
|---|---|
| `download_patterns_corpus` | 按显式 plan 从官方 HF 取有限、多科目样本；已有 corpus 不必重下 |
| `fetch_patterns_sample` | 单文件夹诊断；默认原站，镜像需显式参数，不自动递归或切站 |
| `import_patterns_trace` | 解析 manifest/spec 并编译逻辑读任务 |
| `analyze_patterns_batches` | 专家复用、占用和伙伴互补统计；不是有限时序回放 |
| `report_patterns_batches` | 上述统计的报告图 |
| `run_patterns_replay_study` | 当前注册多窗口、完整权重、四设计、共同供给预算的主实验 |
| `audit_patterns_replay` | 当前主实验的独立核对和报告导出 |
| `run_patterns_flow` | 早期 batch1/batch2 的十回放协议，保留复现，不是当前多窗口入口 |
| `replay_patterns_window` | 早期单窗口五设计回放，保留其 10M-word 保护阈值 |
| `run_endpoint_bridge` 等 | 历史机制/构造研究，不代替真实 trace 主流程 |

所有命令通过 `python -m w2w COMMAND --help` 查看参数；完整列表为 `--list`。
受保护数据的访问仍需有效授权。`--resume` 复用身份核验通过的**完整文件**，
不代表 Python 下载器已实现部分字节 Range 恢复。服务器当前 HF 直连，VPS 隧道停用。

## 修改什么应看哪里

| 修改内容 | 所属层 |
|---|---|
| HTTP、授权、下载限额、源文件身份 | `workloads/patterns_download.py` |
| routing 格式、cohort、专家 union、执行模型 | `workloads/patterns_trace.py` |
| 逻辑读任务、静态地址驻留 | `workloads/read_trace.py`、`read_residency.py` |
| 冻结硬件目录重建 | `synthesis/read_catalog.py` |
| 有限请求与返回执行 | `service/read_replay.py` |
| 注册计划和 CPU 作业编排 | `experiments/run_patterns_replay_study.py` |
| 独立输入/结果约束 | `validation/patterns_replay.py` |
| 报告 / 图形 | `analysis/patterns_replay.py`、`visualization/render_patterns_replay.py` |

主流程不从实验脚本反向导入下载器或硬件目录。历史入口保持兼容导出。
不要把新的研究脚本放回根目录，也不要删除上游工具或另一位开发者的 ASIC 工作区。
环境与部署位置见[服务器说明](../operations/HN072_RESEARCH.md)，全部层次见[代码结构](../CODE_STRUCTURE.md)。
