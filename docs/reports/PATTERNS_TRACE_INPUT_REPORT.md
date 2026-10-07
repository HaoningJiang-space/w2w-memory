# Patterns Behind Chaos 最小真实输入验收

## 证据范围

不是新架构性能实验。将一个获授权原始 expert-selection request 接入已有静态权重读模型。
真实的是 routing；serving batch、权重流量、compute placement 和 memory residency 是显式模型。
没有测得DRAM流量、应用延迟或sharing speedup。当前batch=1也不能检验跨请求expert复用。

## 来源、下载与完整性

论文：[Patterns Behind Chaos: Forecasting Data Movement for Efficient Large-Scale MoE LLM Inference](https://ieeexplore.ieee.org/document/11617553/)，ISCA 2026。
论文摘要直接链接 [HF 数据集](https://huggingface.co/datasets/core12345/MoE_expert_selection_trace)。

- 固定数据集提交：`27febb7b2d24169560a9f6f83d38eb53f94916cf`。
- 文件：`Qwen/Qwen3-235B-A22B-FP8/mmlu/abstract_algebra/93.json`。
- 精确大小：2,627,151 bytes；只下载一个request，未下载模型权重。
- 在所选subject目录第一页的100个条目中最小；不是全数据集的全局最小证明。
- Git blob SHA-1：`c74f079886d952c949edfb0a8ca01c593831220f`，按`blob <size>\0<content>`计算，与HF元数据oid一致。
- SHA256：`eec1bfcf72e8382a13d347879f5c0bbff1fac6387e0d9fbf9b06c3e8ad64312c`。
- [可机读验证记录](../../artifacts/provenance/patterns_trace_input/verification.json)。

访问经历必须区分：eex005镜像返回Cloudflare1010；eex005原站连接失败；本地原站token验证成功但起初GatedRepo拒绝；用户完成数据集授权后，本地原站下载成功。没有发送token到镜像，没有绕过访问限制。

## 格式和转换

完整文件129条token记录、每条94层：第一条prefill矩阵含2行，后128条decode各一行；每行8个互异expert，编号0–127。
全部94层和全部decode格式均通过适配器检查。保留原文件，不把prefill混入decode。

最小转换选择layer `0`、前4个decode步，显式记录省略124步。专家e固定映射到`e % 36`，不从样本训练或重新分配。
128个专家全部参与驻留容量检查，包括这4步未激活的专家。

[执行spec](../../artifacts/provenance/patterns_trace_input/execution.json)依据
[官方模型config](https://huggingface.co/Qwen/Qwen3-235B-A22B-FP8/raw/main/config.json)：
hidden=4096，expert intermediate=1536，128 experts，top-k=8，FP8、128×128 quantization block。
采用三个矩阵FP8 payload加每block一个FP32 scale的**建模假设**：

`W = 3*4096*1536 + 3*(4096/128)*(1536/128)*4 = 18,878,976 bytes/expert`。

没有下载权重验证真实tensor storage；不包含runtime padding、非expert权重、KV/activation/通信/GEMM；不能声称整个模型容量或端到端时间。

单层4步的冷读需求为604,127,232 bytes，单层专家总驻留2,416,508,928 bytes。
每个batch/layer的distinct expert只读一次；下个batch重新冷读。
trace SHA256：`4857e2651f9027a8b918ee152f81a0f319f169eb3177faf518b73d9c50157b7a`。
七个冻结代表设计的静态bank容量/物理路由/字节投影检查全部可行，未运行真实权重的逐字周期回放。

## 接口与复现

模块按层放置：

- `w2w/workloads/patterns_trace.py`：schema、decode batching、distinct专家冷读、固定对象与静态驻留投影。
- `w2w/experiments/fetch_patterns_sample.py`：单目录、固定revision、小文件上限、授权边界、哈希。
- `w2w/experiments/import_patterns_trace.py`：导入CLI，输出现有ReadTrace和可审计demand。
- `tests/fixtures/patterns_input/`：明确标记synthetic的格式/负例，不包含作者raw数据。

命令和输入合同见[方法文档](../methods/PATTERNS_TRACE_INPUT.md)。
原始request仅保存在忽略目录`memory_results/pbc_authorized_raw_v1/`。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest \
  tests.test_patterns_trace tests.test_read_workload tests.test_repository_layout -q
.venv/bin/python -m w2w import_patterns_trace \
  --manifest memory_results/pbc_authorized_raw_v1/manifest.json \
  --spec artifacts/provenance/patterns_trace_input/execution.json \
  --project-designs --output memory_results/pbc_real_import_clean
```

验收测试覆盖输入去重、联合batch、不同request长度/到达、预填充隔离、哈希与维度负例、静态驻留字节守恒、完整字回放、受限下载与凭证域名隔离。远程复跑结果另归档，不能以本地结果冒充eex005执行。
