# Patterns Behind Chaos → fixed DRAM read-demand 输入接口

## 范围和来源

公开输入定义依据作者的 [HF 数据集卡](https://huggingface.co/datasets/core12345/MoE_expert_selection_trace)：每个 request 一个 JSON，顶层列表 index 0 是 prefill；index 1+ 为 decode；每项映射 layer key 到 expert-selection matrix。该格式仅提供路由内容，**不提供 expert 权重字节数、并发到达、batch、存储驻留或 DRAM timing**。

本适配器的实现是独立编写的，不复制作者模拟器，也不引入 FLAME。当前已取得并验证一个获授权作者原始 request；合成样例继续用于边界与负例测试。来源和最小转换结果见 [验收报告](../reports/PATTERNS_TRACE_INPUT_REPORT.md)。

2026-10-07 在 eex005 请求 `https://hf-mirror.com/api/datasets/core12345/MoE_expert_selection_trace` 返回 HTTP403，Server=cloudflare，body=`error code: 1010`。这是镜像客户端特征拦截，不是已确证的 Hugging Face token 问题。官方卡另显示 gated access；这两层不能混同。随后用户提供有效 token 并完成数据集访问授权，已从本地原站取得一个 raw trace；eex005 原站网络连接失败，使用本地下载后传输的方式。没有数据集性能结果。不得通过伪装客户端或其他方式绕过访问限制。

## 接口分为三份输入/输出

1. **文件 manifest**：版本、来源、evidence、request ID、原文件路径、SHA256、逻辑 arrival iteration。文件路径相对 manifest；不存 token 或登录信息。
2. **execution spec**：选中的 MoE layer、完整 expert population、每 expert 实际权重字节、固定 expert→compute 表、batch policy/size、明确的 decode 截断长度。
3. **输出**：`trace.json`（现有 `w2w.read-trace.v1`）、`demand.json`（逐窗口 expert union 和字节）、可选 `residency.json`（冻结架构对应的 bank/memory 字节）。

完整示例在 [tests/fixtures/patterns_input](../../tests/fixtures/patterns_input/manifest.json)，其 evidence=synthetic，不是下载的真实数据。

Manifest 的精确字段：

```json
{
  "schema": "w2w.pbc-files.v1", "evidence": "captured",
  "source": "https://huggingface.co/datasets/core12345/MoE_expert_selection_trace",
  "revision": "填写实际数据集提交号",
  "requests": [{"id": "模型/任务/request标识", "path": "request0.json",
                "sha256": "填写原文件SHA256", "arrival_iteration": 0}]
}
```

执行 spec 的精确字段（下列大小/所有者仅说明 schema，不是大模型参数）：

```json
{
  "schema": "w2w.pbc-execution.v1", "model": "explicit model revision",
  "weight_source": "说明参数量、dtype/quantization、scale元数据如何计入",
  "compute_count": 36,
  "layers": [{"key": "1", "expert_count": 2, "weight_bytes": 3328,
              "top_k": 2, "compute_by_expert": [0, 1]}],
  "batching": {"policy": "iteration_refill", "batch_size": 2,
               "max_decode_steps": 4}
}
```

layer key 必须和 raw JSON 一致，按 `layers` 列表顺序串行。支持 decode 的 `[id,...]` 或 `[[id,...]]`；decode 多行、选中层 null/缺失、非法或重复 expert、top-k 不一致均拒绝。prefill 矩阵被校验并计数，但不混入 decode 需求。`max_decode_steps=null` 保留全部捕获 decode；有限值会记录 omitted 数量，不隐藏截断。

每层当前假设所有 routed expert 等大；不同层可给不同大小。字节必须完整32-byte对齐，不自动舍弃尾部或改精度。compute 映射覆盖未激活 expert，所有对象都参与容量检查。不能用测试激活情况重新选compute。当前不处理未记录的 always-on/shared experts、dense weights、KV；容量声明只覆盖显式选中的 routed layers。

## Batch与执行语义

- `fixed_cohort`：空 batch 时接入最多 batch_size 个已到达 request，直到全组完成才换组；短 request 结束后不补零、不重复使用。
- `iteration_refill`：每个逻辑 decode iteration 开始，按 arrival_iteration、manifest顺序补位；每个驻留 request 贡献它自己的下一步 token。因此同一个 batch 可以包含不同 decode step。
- arrival_iteration 是调用者的逻辑轮次假设，不是测得的墙钟到达；空闲轮次不会被偷偷转换成任意纳秒间隔。需要真实 arrival timing 时须另行提供带时间的执行模型。
- 每层/每批，对 union 中一个 expert **只读一次**完整权重，批内 token 复用；下一批重新冷读，不默认跨批缓存。`expert_token_counts` 与 `logical_read_bytes` 分开输出；前者不乘成整份权重流量。
- 每个 expert 任务在固定compute执行，batch内按expert分组。层 join 后进入下一层、最后一层后进入下一 batch。与真实 GEMM tiling、token dispatch/combine、kernel并发或服务延迟不等价。
- `ReadResidency` 将逻辑对象投影到现有设计的静态 bank 地址，不复制或随请求移动。`--project-designs` 会重建七个冻结代表设计；容量失败单列为 infeasible，不缩小权重。

模型公式是所选层的冷读假设：d_c(t)=sum_{e active, owner(e)=c} W_e。它不是 routing trace 原生给出的流量测量。真正的partial residency、cache miss或tile reread需要改读语义后单独评估。

## 命令

先用小合成格式样例检查接口：

```sh
.venv/bin/python -m w2w import_patterns_trace \
  --manifest tests/fixtures/patterns_input/manifest.json \
  --spec tests/fixtures/patterns_input/execution.json \
  --project-designs --output memory_results/pbc_fixture_import
```

上述产物可直接交给已有回放（需干净提交）：

```sh
.venv/bin/python -m w2w run_read_workload \
  --trace memory_results/pbc_fixture_import/trace.json \
  --output memory_results/pbc_fixture_replay.json
```

真实大型专家可能超过回放 `max_trace_words` 或 bank容量。先导入/投影字节即可；不能把权重统一缩小后称为真实模型回放，也不要盲目把word上限改到数十亿。

镜像仅下载少量文件的入口（在获准访问后使用）：

```sh
.venv/bin/python -m w2w fetch_patterns_sample \
  --endpoint https://hf-mirror.com \
  --prefix Qwen/Qwen3-235B-A22B-FP8/mmlu/abstract_algebra \
  --max-files 2 --max-file-bytes 2097152 --max-total-bytes 4194304 \
  --output memory_results/pbc_raw_sample
```

只查询一个显式目录的第一页，选择该页内最小且满足预算的JSON，不宣称全199GB中的绝对最小；不递归下载、不默认 snapshot。使用固定数据集提交号，核对大小及可得的LFS哈希，保存receipt与文件SHA。访问失败时保留失败receipt，不伪造captured manifest。gated状态默认要求先取得授权文件；也可显式选择原站并指定 `--token-file`，但账号仍必须先完成数据集授权。Token仅发给官方HTTPS域名，跨域重定向移除授权头，不保存到receipt；不自动提交访问条件或切换主机重试。

本轮原站小样本命令（token文件路径由调用者提供，不提交文件）：

```sh
.venv/bin/python -m w2w fetch_patterns_sample \
  --endpoint https://huggingface.co --token-file /path/to/hf_token.txt \
  --prefix Qwen/Qwen3-235B-A22B-FP8/mmlu/abstract_algebra \
  --max-files 1 --max-file-bytes 4194304 --max-total-bytes 4194304 \
  --output memory_results/pbc_raw_new
```

小文件下载器当前原子读取单个有界文件，不提供部分文件续传。只有获得授权后，HTTP Range/curl续传才有意义；不能解决403。取得raw以后，根据实际选层和模型配置另写execution spec，再调用同一个import入口。原始捕获留在忽略的 `memory_results/`；Git只提交代码、协议和有明确证据标签的摘要。

## 验证和当前边界

测试覆盖批内去重、层间依赖、跨批冷读、不同长度request、混合decode位置、固定cohort/补位、flat/2D输入、hash/shape/expert/静态映射错误、容量不缩放、字节到bank守恒、现有完整字执行以及有上限下载/访问失败。

本轮没有更改 endpoint/placement/matching，没有真实工作负载加速结论。已完成一个原始request的哈希/来源/全部94层格式校验，以及单层4步的静态字节投影。下一步可以少量增加独立request并比较batch size；不能重复一个request伪装成多个独立用户。
