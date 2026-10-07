# 有限任务完成时间与共享成本：首轮冻结实验

2026-10-07。结果代码 `17a64420eaada660c8ce159b00f7843f08059431`，eex005 干净隔离
目录 `/home/wangziheng/Video/w2w-finite-read-20261007`。Python 3.13.13，单线程数值库。

**共享是否值得，取决于关键任务的必需资源是否空闲，以及请求能否持续供给；静态复用则在
所有已测流量中保留相同服务。** 这轮出现正收益、无收益和小幅退化，没有一种结构全面获胜。
主要发现不是要继续增加 endpoint，而是原长期服务收益会被有限 credit 与阶段同步明显压缩。

## 与技术报告及现有硬件证据的关系

已核对 Git `5e06bc0` 归档的 [W2W_MEMORY_SERVICE_TECHNICAL_REPORT v1.0](W2W_MEMORY_SERVICE_TECHNICAL_REPORT.pdf)，
SHA-256 `2b6c8bf36e9fc76334c944d4d2cda4baccbccf4239285423ccad95a957e6e3cb`。
其 §9–12 的三方案、时钟边界和任务闭环要求作为本轮解释依据。Private / Paired-Duplicated /
Paired-Configurable 是主比较，k2 和宽 direct 保留作强参考。PDF 原文和 SHA 没有改写。

PDF 使用的 35.6% / 16.3% 与 hold/cap 未闭合属于历史映射状态。
[最新 ASIC 报告](ENDPOINT_ASIC_SLICE_REPORT.md)已经给出同 Nangate45、2 ns、提取后修复结果：
source 21,987.294 → 15,318.674 μm²，绝对减少 6,668.620 μm²（30.33%）；
加相同的特化 Home RX 与两个 Shared RX，46,023.320 → 39,354.700 μm²（14.49%）。
这些是局部规定边界的独立硬件证据，不是本轮任务模型的总系统成本。

系统 bit-budget 回放使用 1.024 ns 原生槽、每路两个整字 RX credit；RTL 额外有 held-beat
寄存器，RX 为 Home 256-bit / Shared 384-bit reservoir。这轮没有把两者宣布为逐周期等价，
也没有把 2 ns 面积与 1.024 ns 带宽相乘。主表用原生槽，图中不用物理 TB/s 或 area-delay。
Nangate45 也未解决源端外围数字逻辑到实际 memory 工艺的映射。

## 固定工作与检查

按[预注册方法](../methods/FINITE_READ_STUDY.md)，沿用 H/plus、36C+36M、每 M 32 banks 和七个
已冻结设计。各结构使用自己的合法驻留；所有设计使用同样的对象、compute 所有者、字地址、
任务依赖、有限请求和 RX 条件。不重选配对、数据比例、位宽或深度。
长任务每 C 读 2,496 个 32-byte 字，读后计算 8 槽；short9 只读 64 字；straggler9 的 C14
读四倍数据，join 后再计算 32 槽。所有场景保留未活动对象的静态容量。
活动组按几何列与列内行坐标选取，保留真实半行错位与边界，没有按共享关系挑 seed。

完成 **77 次回放、22 组 duplicated/configurable 对照、49 项定向测试**。
77 次合计完成 2,904,384 个模型字；每槽请求/字/bit/credit 守恒，全部必要任务完成。
两对实现的驻留、逐任务时间、路由计数、停顿及交付事件哈希完全一致。
这不是本轮新增 290 万字 RTL payload 仿真；RTL 功能证据沿用原独立归档。

独立分析重新核对原始文件 SHA、trace/design/residence 哈希、路由/原生/交付总量和摘要一致性。
Private 的七个主场景还与解析完成时间一致。关键路径沿实际依赖与 compute 串行边回溯，
read wait、compute 和 release 等待之和等于 makespan；并行任务等待总和不作墙钟时间。

首次启动误将错位 H/plus 当成普通 6×6 网格，入口拒绝后即停止，未产生候选性能。
`17a6442` 改为每列内排序并补回归；失败启动日志一并归档。输入定义未按性能修改。

## 主结果：任务完成时间

下表均为原生槽，越小越好。A/B duplicated 的时间与对应 configurable 完全相同。

| 场景 | Private | k2 direct | k3 wide | A configurable | B configurable |
|---|---:|---:|---:|---:|---:|
| single | 88 | 68 | 68 | 79 | 77 |
| dispersed9 | 88 | 88 | 68 | 79 | 77 |
| clustered9 | 88 | 88 | 88 | 89 | 89 |
| full36 | 88 | 88 | 88 | 89 | 89 |
| moving9 | 352 | 352 | 352 | 356 | 356 |
| straggler9 | 354 | 275 | 275 | 319 | 310 |
| short9 | 4 | 4 | 3 | 4 | 4 |

![冻结场景的完成时间](../../artifacts/figures/finite_read/completion.svg)

- **分散热点**：B 为 77 槽，对 Private 88 槽缩短 12.5%（1.143×）；A 为 79，宽 k3 为 68。
  k2 的九个任务中，C0/C2/C4/C12/C24 仍要求 private-bank 字节，整阶段仍等到 88 槽；
  不能用其他四个先完成节点的带宽均值替代 join。
- **相邻热点及四阶段移动**：每个 3×3 阶段的 k3 有六个客户端的伙伴同时活跃。
  即使另三个先完成，join 仍等待繁忙 pair。B 为 89 对 88；四阶段累加为 356 对 352。
  热点会移动这件事本身，不保证共享有效。
- **全忙**：B 同样多一个有限执行槽，没有额外原生能力可借。
- **长尾**：B 的关键读等待从 314 降到 270 槽，加相同 40 槽计算后为 310 对 354。
  k2 / 宽 k3 都为 275 槽；该次关键任务 C14 不依赖 private bank，k2 因而有很好的成本位置。
  这仅说明该固定长尾位置的机制，不代表任意 straggler 都一样。
- **短读**：A/B 都为 4 槽，与 Private 相同；宽 k3 为 3 槽。条带尾部、起始延迟与离散槽
  已能改变长期服务排名，不能把 1.482 TB/s 等周期结果直接当任务加速比。

## 控制实验：先区分供给不足与共享竞争

只把 outstanding 从 128 提到 512 words/C，issue 上限仍为 64；位宽、source/RX 深度、地址
和所有延迟不变：

| 场景 | Private 128→512 | k2 128→512 | k3 wide 128→512 | A 128→512 | B 128→512 |
|---|---:|---:|---:|---:|---:|
| dispersed9 | 88→88 | 88→88 | 68→49 | 79→62 | 77→60 |
| clustered9 | 88→88 | 88→88 | 88→88 | 89→88 | 89→88 |
| full36 | 88→88 | 88→88 | 88→88 | 89→88 | 89→88 |

![同一模型的 credit 控制](../../artifacts/figures/finite_read/credits.svg)

分散流量中 B 可到 60 槽，对 Private 缩短 31.8%（1.467×），而相邻热点仍无显著改善。
这直接支持两个不同原因：前者受请求窗口影响，后者有必需资源竞争。512 不是免费改进，
新增 request tracking 等逻辑尚无面积证据，不把它与 128 的方案放进同硬件预算排名。
控制后的 source-full/RX-full 计数表明瓶颈可能转移；不同单位的 stall 可重叠，不能相加当时长。

RX ready 改为 `(1,1,0,0)` 时，dispersed9 的 Private/k2/wide/A/B 分别为
165/165/88/113/105 槽。它验证有限 RX 反压影响和同服务复用，没有证明实际长线 credit 协议：
模型尚无独立的反向 credit 传播时延。共享结构也制造了更多独立 RX，不能把相对减速差全部
归因于更高 DRAM 带宽；RX 资源已在原始结果中另计。

## 成本与取舍

以下是每 memory 重复模板的既有代理账本，不能与 μm² 相加。

| 设计 | Lane bits/M | TX buffer proxy bits/M | Access wire bit-mm/M |
|---|---:|---:|---:|
| Private | 8,192 | 8,192 | 120,832.0 |
| k2 direct | 16,384 | 8,192 | 241,561.6 |
| k3 wide direct | 24,576 | 8,192 | 474,163.2 |
| Paired A duplicated | 16,384 | 24,576 | 297,497.6 |
| Paired B duplicated | 18,432 | 40,960 | 341,664.0 |
| Paired A configurable | 16,384 | 16,384 | 297,497.6 |
| Paired B configurable | 18,432 | 24,576 | 341,664.0 |

B configurable 对 duplicated 只减少一套 TX machinery；物理 lane 与长线没有减少。
模型 TX buffer 差也不包含 RTL 的所有输出拍/接收状态。
原始结果同时列出 pipeline、selector、HB、RX payload allocation 与未校准控制项。

只投影到 `makespan + lane + TX buffer + wire bit-mm`：

- single 和 straggler9 的前沿为 Private、k2。
- dispersed9 的前沿为 Private、A configurable、B configurable、宽 k3。
- clustered9、full36、moving9 为 Private。
- short9 为 Private、宽 k3。

这解释了为什么不能预设 k3/configurable 全面获胜。投影没有涵盖 selector/control/实际 RX
与驱动全部成本，因此不是完整系统 PPA 的支配证明；也不是设计族全局最优。

## 下一步收束

本轮完成了技术报告要求的有限任务机制诊断，**尚未完成 §10/§12 的真实应用闭环**。
后续优先捕获一个明确内存阶段的实际对象读请求，保留训练/测试分离、计算归属和冻结地址，
检查关键任务的伙伴共同忙闲与 outstanding 需求。首先回答真实请求是否落在本轮的有利区域。
无需为了推进而增加新的 FIFO、placement 或匹配算法。

真实阶段回放仍须逐项落实地址相关原生时序、请求/返回控制通路、反向 credit 延迟、跨源身份
与完成合并，以及与目标端点一致的时钟/缓冲。没有这些条件，不将本轮合成槽数写成 LLM
端到端时间，也不将已有局部面积外推成 wafer 节省。

## 复现与文件

```sh
# 在 eex005 的干净 checkout；原执行源码为 17a6442。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m w2w run_read_workload --suite --output memory_results/finite/study
# 分析器新增独立归档核对，绘图不会再次求解服务或选择设计。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m w2w.analysis.read_completion memory_results/finite/study/summary.json --output memory_results/finite/figures
```

[紧凑摘要及全部原始回放](../../artifacts/results/workload/finite_read/)、
[测试/执行/独立核对凭据](../../artifacts/provenance/finite_read_manifest.json)。
