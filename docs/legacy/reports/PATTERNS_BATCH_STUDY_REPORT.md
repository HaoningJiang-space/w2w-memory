# 真实 MoE routing：批处理诊断与 CPU 完整读回放

2026-10-07。实验源码 `b7490e81c43bfc78ba1570cbaa7fdbe956037ac0`，干净 `main`。
本轮在 `hn072@143.89.78.72`（hostname `ee4e072`）直接下载并用 CPU 验证，未使用 GPU。
项目目录 `/Projects/haoning/w2w-trace-20261007`；未改动同服务器的 ASIC 工作目录。

## 1. 实际取得的数据

数据源为 [Patterns Behind Chaos 官方 inference routing dataset](https://huggingface.co/datasets/core12345/MoE_expert_selection_trace)，
固定 revision `27febb7b2d24169560a9f6f83d38eb53f94916cf`。
本轮只取 Qwen3-235B-A22B-FP8 / MMLU 八科，各 32 个不同 requests：

| 科目 | 目录列出的 JSON 数 | 实际请求数 | 原始字节 |
|---|---:|---:|---:|
| abstract_algebra | 100 | 32 | 99,668,204 |
| computer_security | 100 | 32 | 93,314,865 |
| professional_medicine | 272 | 32 | 161,787,602 |
| philosophy | 311 | 32 | 92,820,001 |
| high_school_biology | 310 | 32 | 96,248,750 |
| high_school_physics | 151 | 32 | 108,881,816 |
| moral_scenarios | 895 | 32 | 98,881,615 |
| business_ethics | 100 | 32 | 97,366,289 |
| **总计** | | **256** | **848,969,142** |

这是约 849 MB / 0.791 GiB，不是全量 199 GB。用户允许的约 12 GB 是上限，
本轮不为凑大小额外下载。另保留此前独立的 request93（2,627,151 bytes）作为回放参考，
合计 257 个文件、851,596,293 bytes。

抽样在各科目的首个非递归目录页内，以固定 seed=20261007 对路径排序后取 32 个，
不按观察到的 routing 或文件最小排序。单文件上限 32 MiB；八个目录均 **0 个因大小排除**。
这不是全模型、全任务的代表性随机样本，目录页范围写入 receipt。

每个文件重新核对：HTTP 返回内容长度、固定 revision 的 Git blob OID、SHA256；
256 个 source ID 与内容 SHA256 都唯一。全部 94 层、128 个 decode 步通过格式检查，
prefill 与 decode 分开，没有把错误页当 trace、没有复制请求或补齐序列。
服务器与本地独立下载的文件哈希全部相同。

HF 原站在此服务器可直接访问；此前 eex005 的镜像 403 已不再阻塞这条下载路径。
使用用户已授权的 token，经 SSH stdin 进入进程内存，不写服务器 token 文件，不发送给镜像。
下载可按 receipt 复用已完成且哈希正确的文件；**不声称支持文件内部的 Range 断点续传**。
原始 routing 不入 Git，Git 只保存代码、清单、校验和与聚合结果。

## 2. Routing 到 demand：哪些来自观测，哪些来自模型

观测是逐 request / decode step / layer 的 expert 选择。
后续执行采用冻结假设：

1. 固定 cohort batch=1/2/4/8/16/32/64/128，不假装观测到了 continuous batching 时间。
2. 每个 batch/layer 内同一 expert 权重只冷读一次，跨 batch 再次冷读；去重的是 expert union。
3. compute owner 为 `expert_id % 36`，另有两个固定平衡映射作敏感性。
4. 每 expert 为 18,878,976 bytes：三组 FP8 权重及模型 FP32 block scales。
   全部 128 个 experts 都计入该层容量；不以活动集缩小存储量。
5. 使用既有 H/plus 与 18 对固定共享伙伴，没有按新数据重新训练 placement 或配对。

没有下载模型权重或执行神经网络。这里的“完整权重读取”指按注册权重尺寸生成全部
地址/字数的模拟读流；交付哈希验证模拟请求的完整性，不是对真实 learned weight 内容做比对。

统计使用全部 128 步、预注册 8 层 `0,13,26,39,52,65,78,93`。
四组 request 编组、三组映射产生 96 个混合统计配置；另有 48 个单科目和 64 个单层配置。
这些共享 requests，不能当成独立重复样本；所报范围是敏感性，**不是置信区间**。
尤其 B=128 每个编组次序只有两个 cohort，不能据此声称大 batch 的总体统计已充分收敛。
本轮没有训练优化器，因此不需要拿 train/val/test 的名字替代真实的样本独立性。
未来若用这些数据选择硬件或配对，必须另外冻结独立 requests/任务作为最终测试。

## 3. 实际诊断：复用越高，不代表共享机会越大

下表为默认映射、四个编组次序的均值。复用节省对照是“每个 routed token 都完整读专家权重”，
不是实测 DRAM 流量。

| Batch | Distinct experts | 批内权重复用节省 | 活跃 compute / 36 | 活跃客户端的伙伴空闲比例 | Home/pair memory-only 完成下界之比 |
|---:|---:|---:|---:|---:|---:|
| 1 | 8.00 | 0.00% | 7.42 | 82.04% | 1.566 |
| 2 | 15.12 | 5.53% | 13.03 | 65.16% | 1.550 |
| 4 | 27.15 | 15.14% | 20.63 | 42.88% | 1.396 |
| 8 | 45.00 | 29.69% | 28.32 | 21.05% | 1.291 |
| 16 | 66.91 | 47.73% | 33.44 | 7.00% | 1.192 |
| 32 | 87.86 | 65.68% | 35.45 | 1.52% | 1.074 |
| 64 | 103.87 | 79.71% | 35.91 | 0.25% | 1.012 |
| 128 | 114.40 | 88.83% | 35.98 | 0.05% | 1.001 |

最后一列只比较两个忽略 endpoint/HB/credit 的 memory service 下界，
**不是已执行的加速比，也不是一般意义的系统性能上界**。

![Batch reuse and sharing](../../artifacts/figures/patterns_batch/batch_reuse_and_sharing.svg)

控制活跃数量后，伙伴互补没有想象中那么特殊：对 k 个活跃 compute，均匀随机标签下，
一个活跃客户端的伙伴空闲概率为 `(36-k)/35`，跨窗口按活跃客户端数加权。
B=1 实际为 82.04%，该零假设为 81.48%，只多 0.56 个百分点；B=4 实际 42.88%，
零假设 43.24%。不能把低 batch 的稀疏性说成已经发现强烈、可学习的专家反相关性。

B=1 的伙伴持续空闲事件平均约 1.70 decode 步、P95=4 步；B=16 约 1.45 步、P95=3 步。
这些是同一 cohort、同一层、同一 compute 内的连续步数，没有时戳，不能换成持续微秒。

任务域也有影响：B=32，八科单独 batching 的空闲伙伴比例范围为 2.51%–13.23%，
而混合任务只有约 1.52%。不能只用混合平均替代任务域差异。
B=1 的三种映射/四次编组范围为 81.13%–83.04%；单层范围 78.48%–84.93%。
完整范围、原始聚合数与图可按下方入口复现。

## 4. 真正打通的执行链

```text
服务器原站 JSON + 固定 revision/哈希
 → request/step/layer 解析
 → 固定 batch 的 distinct-expert union
 → 完整专家权重读 DAG（全部专家静态容量）
 → 冻结 expert owner 与 bank residency
 → 有限 request credit / native service / endpoint / HB / RX
 → 逐字守恒与完成记录
```

两个窗口均 layer0、decode 第一步：B=1 为此前 request93；B=2 为预注册 corpus manifest
前两个独立 requests。它们内容不同，**不能用两者的耗时比推断 batch-size 效应**。
B=1 读取 8 个 experts / 151,031,808 bytes / 4,719,744 words；
B=2 读取 16 个 experts / 302,063,616 bytes / 9,439,488 words。
这个 B=2 窗口没有重复专家；去重复用的统计证据来自上面的全批量分析与独立单元测试。

五设计×两窗口共 **10 次完整回放全部完成**；每个读字都交付且无多发/少发。

| 设计 | B=1 完成槽 | B=2 完成槽 | Bank-port 连接 | 配置 HB TB/s | Endpoint storage bits / memory |
|---|---:|---:|---:|---:|---:|
| Home | 36,878 | 55,317 | 32 | 1 | 8,192 |
| k2 direct | 36,878 | 46,098 | 64 | 2 | 8,192 |
| k3 direct | 27,660 | 46,100 | 96 | 3 | 8,192 |
| k3 buffered (160-bit Shared) | 31,678 | 50,117 | 96 | 3 | 40,960 |
| k3 configurable shared egress | 31,678 | 50,117 | 96 | 3 | 24,576 |

每个窗口，duplicated buffered 与 configurable shared egress 的任务、路由、delivery hash、
stall、native 使用和完成记录逐项一致；后者存储 40,960→24,576 bit，但还有方向选择器成本。
此处 storage 不含 pipeline/RX 等，完整成本账本保留在每个结果中，不能把它当整个系统面积。

B=1：k2 与 Home 相同，k3 direct 对 Home 的读阶段完成比为 1.333×；
B=2：k2 为 46,098 槽、k3 direct 为 46,100 槽，更高连接成本没有额外收益。
这两个有限窗口的结果不构成架构总体排名；更不能把 bank-only 下界之比当成这里的实测值。

[完整读输入、逐设计结果与 flow summary](../../artifacts/results/workload/patterns_batch/flow/)。

本轮 time unit 是机制模型原生槽；没有用局部 ASIC 的 2 ns 直接换算整片时延。
未模拟 GEMM、KV、token dispatch/combine、缓存复用或完整 DRAM timing。
因此这里只证明 routing→完整读阶段→有限接口执行已经贯通，不宣称端到端 LLM 加速。

## 5. 正确性与复现

服务器和本地均通过 44 项定向测试。新环境 Python 3.10 与本地浮点求和存在末位差异，
仅对归档 `wire_mm/access_wire_bit_mm` 允许极小舍入误差；连接、存储、位宽、容量等仍精确核对。
专门测试拒绝真实资源变化。跨主机批量诊断的全部非浮点项一致，最大浮点差
`8.881784197001252e-16`。

同一个 B=1 窗口与此前 eex005 回放逐设计比较，完成槽数、字节、delivery hash、
residency hash、审计和 stall 全部一致。trace 总哈希因 source manifest 的文件路径变化而不同；
读对象、任务、execution spec 与配置一致，该区别单独记录，不伪称文件身份完全相同。

在新服务器的项目目录使用 `.venv/bin/python`：

```sh
# 下载：从安全 stdin 输入 token；仅复用已经完成且校验正确的文件
.venv/bin/python -m w2w.experiments.download_patterns_corpus \
  --plan artifacts/provenance/patterns_batch/plan.json \
  --output memory_results/pbc_corpus256 --token-stdin

# 使用新的输出目录，不覆盖历史结果
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m w2w.experiments.analyze_patterns_batches \
  --manifest memory_results/pbc_corpus256/manifest.json \
  --plan artifacts/provenance/patterns_batch/plan.json \
  --output memory_results/pbc_batch_analysis_new

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m w2w.experiments.run_patterns_flow \
  --single-manifest memory_results/pbc_authorized_raw_v1/manifest.json \
  --corpus-manifest memory_results/pbc_corpus256/manifest.json \
  --output memory_results/pbc_real_flow_new --workers 2

.venv/bin/python -m w2w.analysis.report_patterns_batches \
  --summary artifacts/results/workload/patterns_batch/summary.json.gz \
  --output artifacts/figures/patterns_batch
```

先提交代码再跑；runner 要求干净工作树。独立虚拟环境，不改系统 Python，无 GPU 依赖。
当前 CPU/RAM 共享使用，最多两个 replay worker。源目录及原始数据不放入别人的 ASIC 工程。

归档：

- [实验注册与限制](../methods/PATTERNS_BATCH_STUDY.md)
- [下载清单、receipts、双重哈希与跨主机核对](../../artifacts/provenance/patterns_batch/)
- [256 请求统计](../../artifacts/results/workload/patterns_batch/summary.json.gz)
- [指标表与图](../../artifacts/figures/patterns_batch/)

本轮研究含义是：真实 inference routing 在低 batch 下确有可观察的空间空闲机会，
但随着 batch 增大，权重复用与共享机会朝相反方向变化。下一次性能实验应先冻结目标
batch/任务域与执行假设，再扩展多个独立读窗口；不能把本轮两个窗口当最终架构排名。
