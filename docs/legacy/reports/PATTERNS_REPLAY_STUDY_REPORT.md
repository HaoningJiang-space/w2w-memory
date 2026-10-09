# 真实 routing 的多窗口完整读阶段回放

2026-10-07，CPU 服务器 `hn072@143.89.78.72`。本轮遵循
[实验前冻结的协议](../methods/PATTERNS_REPLAY_STUDY.md)，不新增架构、调参或下载。
执行源码为干净提交 `aa9d91115ceff4458789487d0ed72a2796cd5277`；
独立输入与结果审计源码为 `cde90e5bc83813eb030e031dd642d21cf87f832d`。

## 输入与研究口径

沿用 [256-request corpus](PATTERNS_BATCH_STUDY_REPORT.md)，Qwen3-235B-A22B-FP8 / MMLU
八科，固定数据集 revision `27febb7b2d24169560a9f6f83d38eb53f94916cf`。
再次逐文件核对全部 256 个 SHA-256：ID 和内容均唯一，总计 848,969,142 bytes。
原始 routing 留在服务器，不随 Git 归档；小规模输入已经足够完成本轮注册实验，未凑满 12 GB。

按固定 seed8301 的路径哈希排序选取三个互不重叠的 16-request groups，共 48 个独立 requests。
每组八科各两条；组内 batch=1/4/16 使用嵌套前缀。
g0 为 layer0 / decode17，g1 为 layer39 / decode65，g2 为 layer78 / decode113。
原始步号保留，每个窗口独立冷启动；未执行前序步，不模拟 continuous batching 的到达时刻。

执行模型仍是固定 `expert_id % 36` compute owner；每批每层对激活 expert 去重，
每个 expert 完整读取 18,878,976 bytes，全部 128 个 experts 始终计入静态容量。
没有权重复制、运行时迁移或为加速模拟而缩小权重。没有下载真实 learned weight 内容：
这里读取的是按注册模型尺寸生成的完整逻辑地址流。

真实观测只决定 expert selection。权重冷读、复用、owner、驻留与硬件时序均为显式模型，
因此下文报告的是**真实 routing 驱动的读阶段模拟完成时间**，不是实测 DRAM traffic、
GEMM 时间、token latency 或端到端 LLM speedup。三组层和步不同，不作总体置信区间。

## 比较设计与正确性

固定 Home、k2 direct、k3 direct、Configurable B 四个既有设计。
九个窗口统一 `outstanding=192` 为主比较，g0 三窗口另以统一 128 作配对控制：
36 主回放 + 12 控制回放。192 来自独立请求窗口研究，未用本轮 trace 搜索最优 N；
不声称它在所有窗口都完全消除了供给瓶颈。

所有设计 issue=64 words/compute/slot，RX depth=2，request/native/link latency=1/0/1。
请求窗口变化不改变每个设计的数据驻留；不同设计使用各自冻结布局，没有按活动集重新放置数据。
四个 CPU workers 执行，不使用 GPU。

审计包括：

- 注册的九窗口、48组合精确覆盖，没有缺失、重复或额外样本替代。
- 从原始 selected-token JSON 独立重算专家 union、token counts、完整读字节和未激活专家容量；
  再调用编译器重建 trace，核对冻结 trace/demand 身份。
- 每份压缩回放 SHA-256、字节长度及 summary 一致；任务完整、读字与路由/native/HB 守恒。
- 执行器逐槽守恒和冻结驻留证书；每任务及总完成时间满足重新计算的 request-window 必要下界。
- 配置与成本账本重算，N128/N192 的 residence hash 保持不变。

**48/48 回放全部完成，1,094,980,608 words 全部交付（每字 32 bytes）。**
服务器原始输入重编译审计通过；本地回传文件哈希核对与全部 48 记录复核通过。
执行墙钟约 44.2 分钟，四 worker；这不是被模拟的读阶段时延。
63 项定向测试通过，涵盖 routing、union、容量、驻留、读执行、请求窗口、归档与命令导入。

审计开发中修正了 JSON 字典整数键转字符串、tuple 转 list 两种比较问题；
修正只规范化序列化表示，没有修改原始 routing、回放字节、硬件参数或完成时间。


## 九个窗口的完整结果

时间单位为模型 slot。主比较统一 N192；每行使用同一窗口、相同逻辑读数据。

| 窗口 | Distinct experts | 完整读 bytes | Home | k2 direct | k3 direct | B | Home/B |
|---|---:|---:|---:|---:|---:|---:|---:|
| g0_b1 | 8 | 151,031,808 | 36,878 | 18,442 | 18,442 | 23,642 | 1.5599 |
| g0_b4 | 31 | 585,248,256 | 55,317 | 36,881 | 36,881 | 42,081 | 1.3145 |
| g0_b16 | 82 | 1,548,076,032 | 73,756 | 64,538 | 64,538 | 67,138 | 1.0986 |
| g1_b1 | 8 | 151,031,808 | 36,878 | 36,878 | 18,442 | 23,642 | 1.5599 |
| g1_b4 | 30 | 566,369,280 | 36,878 | 36,878 | 36,879 | 36,878 | 1.0000 |
| g1_b16 | 67 | 1,264,891,392 | 73,756 | 64,538 | 64,538 | 67,138 | 1.0986 |
| g2_b1 | 8 | 151,031,808 | 55,317 | 27,663 | 27,663 | 35,463 | 1.5599 |
| g2_b4 | 31 | 585,248,256 | 55,317 | 36,881 | 36,882 | 42,081 | 1.3145 |
| g2_b16 | 78 | 1,472,560,128 | 73,756 | 73,756 | 55,321 | 60,520 | 1.2187 |

![Registered full read windows](../../artifacts/figures/patterns_replay/read_completion.svg)

三个 batch1 窗口中，k3 direct 对 Home 约 2.00×，B 约 1.56×；k2 有两组约 2.00×，
一组无收益。B 在 batch4 是 1.00–1.31×，batch16 是 1.10–1.22×。
这些是已注册窗口的取值，不是全模型总体收益范围。

不能把结论写成“batch 越大，收益严格单调下降”：g1 在 batch4 无改善，batch16 又有改善。
它取决于专家分布及最慢 compute 的固定伙伴，而不只取决于活动数量。
k3 在 g1_b4 比 Home 多一个槽；保留这个有限执行尾部差异，不四舍五入成所有情形都不退化。

k2 在 g0 的三个窗口与 k3 完成时间相同，以较低成本提供了相同服务；
但 g1_b1 和 g2_b16 的 k2 没有收益，k3/B 则有。**不能用一个窗口宣布某个设计总体最优。**
B 在这些窗口没有超过宽 k3 的读速度，其价值需结合更窄出口/接入线和更多缓冲评估。

## 请求窗口控制：共享收益不能与供给预算混淆

同一 g0 窗口、相同设计和驻留，只把每 compute 最大 outstanding 从 128 改为 192。
以下为 N128 → N192 完成槽：

| Batch | Home | k2 direct | k3 direct | B |
|---:|---:|---:|---:|---:|
| 1 | 36,878 → 36,878 | 27,660 → 18,442 | 27,660 → 18,442 | 31,678 → 23,642 |
| 4 | 55,317 → 55,317 | 46,099 → 36,881 | 46,099 → 36,881 | 50,117 → 42,081 |
| 16 | 73,756 → 73,756 | 69,147 → 64,538 | 69,147 → 64,538 | 71,156 → 67,138 |

Home 不变，三个共享设计均有改善。因此只给新设计更大的请求窗口，会错误地把
请求供给改善算作接口结构收益。本轮主比较给所有设计相同 N192，并报告控制。
192 不是普遍充分条件；仍有 credit/RX 等阻塞记录。资源 stall 是多资源计数，
不能直接相加当成全局丢失周期。必要下界与完成时间的差也不能全部归因于 endpoint：
下界没有完整表示 compute 内任务顺序及资源之间的时间耦合。

## 成本账本与可支持的判断

下列是**每颗 memory 重复模板**的代理，非综合 PPA。全部资源字段在原始结果中保留。

| 设计 | Bank-port edges | Export lane bits | Endpoint storage bits | Pipeline register bits | Wire mm | Access wire bit-mm | 配置 HB TB/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Home | 32 | 8,192 | 8,192 | 63,488 | 472.0 | 120,832.0 | 1 |
| k2 direct | 64 | 16,384 | 8,192 | 126,976 | 943.6 | 241,561.6 | 2 |
| k3 direct | 96 | 24,576 | 8,192 | 248,320 | 1,852.2 | 474,163.2 | 3 |
| B | 96 | 18,432 | 24,576 | 179,008 | 1,852.2 | 341,664.0 | 3 |

B 相比宽 k3，export lane bits 少 25%，接入 wire bit-mm 少约 27.9%，
但 endpoint payload storage 为三倍，并有方向选择、缓冲、RX、请求状态等额外成本。
不能把这些不同单位加成总面积，不能用 wire proxy 宣称总体更便宜。
B 的局部 ASIC 证据保持此前独立范围；不把局部 2 ns 时序换成本轮整片 slot 时延。
本轮也没有重做 duplicated/configurable RTL 等价，旧等价证据按原合同引用。

本轮足以支持：真实 routing 经显式执行假设后，能够产生可利用的局部服务不均；
现有有限回放能兑现部分共享收益，且成本较低的 k2 在部分窗口仍是强参考。
它尚不支持 B 普遍优于 k2/k3、全局最优 placement，或端到端推理加速。
下一轮若优化硬件或 owner，需要另设独立测试 requests，不能再把本轮结果当未见测试集。

## 复现与代码整理

主开发在本地，推送唯一 `main` 后服务器拉取运行；见[工作流](../operations/HN072_RESEARCH.md)。
原执行目录保持 `aa9d911`，没有把正在运行的 checkout 更新成新版本。
当前主工作区为 `/Projects/haoning/w2w`，`memory_results` 链接到原始运行数据。

```sh
cd /Projects/haoning/w2w
# 复核现有结果，同时重新解析原始 routing：
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w audit_patterns_replay   --source memory_results/pbc_multiwindow --verify-inputs   --output build/patterns_replay_audit

# 重新执行注册实验需干净提交、新输出目录：
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m w2w run_patterns_replay_study   --manifest memory_results/pbc_corpus256/manifest.json   --output memory_results/pbc_multiwindow_rerun
```

流程完成后将公共设计目录移至 `synthesis/read_catalog.py`，审计移至
`validation/patterns_replay.py`，绘图移至 `visualization/render_patterns_replay.py`；
`analysis/patterns_replay.py` 仅导出报告并保留原 CLI/API 兼容入口。
新增流程命令全部注册到 `python -m w2w --list`。见[分层入口](../CODE_STRUCTURE.md)。

- [原始回放与冻结输入](../../artifacts/results/workload/patterns_replay/flow/)
- [服务器含原始 routing 重编译的审计](../../artifacts/results/workload/patterns_replay/audit.json)
- [48 行对照表](../../artifacts/results/workload/patterns_replay/replays.csv)
- [注册协议与验证 provenance](../../artifacts/provenance/patterns_replay/)
- [服务器环境、全 corpus 哈希复核与直连实测](../../artifacts/provenance/hn072_setup/)

Git 归档包含完整逻辑 trace、spec、demand、manifest、48 份 gzip 回放、summary 与日志。
manifest 的原始 JSON 相对路径按服务器布局保留；Git 中不包含授权原始 JSON。
本地可对 `artifacts/results/workload/patterns_replay/flow` 运行相同审计而不加
`--verify-inputs`，只复核已归档输入/结果；不能把这种复核称作重新获取了真实 routing。

整理提交 `c83ad536b1a2e362b881ccd61b7d0795a9d3cc5c` 已同步服务器；整理前后七设计身份完全相同，
两端 63 项测试通过，全部 48 个审计记录及 CSV 内容完全相同；服务器再次完成原始输入重编译。
