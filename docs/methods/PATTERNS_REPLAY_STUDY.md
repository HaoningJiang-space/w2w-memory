# 多窗口真实路由读阶段：固定协议

本轮扩大已完成的输入闭环，不修改 endpoint、布局、仲裁、expert owner 或权重尺寸。
使用已下载的 256-request corpus，不新增下载。实验前冻结
`artifacts/provenance/patterns_replay/plan.json`，包括全部 source IDs；不按模拟收益选窗口。

## 范围与样本

- 八科各按 seed8301 的路径 SHA 排序取前六个 requests，组成三个互不重叠的 16-request groups。
- 每组含每科两个请求；两轮各一个/科，科目顺序按固定哈希排列。
- 每组取嵌套的前 1/4/16 个 requests，组内使用同层同 decode 位置。
- g0: layer0 / decode17；g1: layer39 / decode65；g2: layer78 / decode113。
- 九个单层窗口独立冷启动，前序 decode 不执行，原始 JSON 不改写；保留原始步号。
- 每层全部 128 个专家保持静态驻留；每个被激活专家完整读 18,878,976 bytes。
- 不推断 continuous batching、缓存命中、真实 DRAM traffic 或 GEMM/LLM latency。

三组不是充分的总体样本，层和步在组间也不同；报告每组明细及范围，不给总体置信区间。
同一组内 batch 嵌套有意共享 requests，是配对敏感性分析，不能当独立样本。

## 比较与正确性

固定四个既有设计：Home(0)、k2 direct(1)、k3 direct(2)、B configurable(6)。
不重复完整 duplicated/configurable 全目录；此前十回放已验证同请求同服务记录，
本轮继续保留原设计和数据布局，不声称新增 RTL 等价证明。

主比较统一每 compute `outstanding=192`；g0 的三个 batch 再统一用128作对照。
192取自独立的合成 request-window 研究，不由本轮 routing 调参；不声称它在所有真实窗口都充分。
所有设计的 issue=64 words/slot、RX depth=2、request/native/link latency=1/0/1 不变。
总计36主回放+12控制=48回放，四个CPU workers。max_words=80,000,000，max_slots=500,000；
扩大的是运行保护阈值，不修改数据或服务能力，超过则失败，不自动抽样或缩权重。

每次执行使用已有逐槽守恒检查，并以新近归档的 request-window necessary bounds 检查
每个任务和总完成时间。结果保存完整 trace/residence/design 身份、delivery hash、
stall、字数、成本、请求窗口与资源下界。更改N必须不改变residence。

指标为读阶段makespan及相同窗口对Home的比值，同时报告连接、lane、wire、buffer和N。
不混成未经校准的总面积分数；不把局部ASIC的2ns直接换算成本轮整片时延。

运行：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m w2w.experiments.run_patterns_replay_study \
  --manifest memory_results/pbc_corpus256/manifest.json \
  --output memory_results/pbc_multiwindow
```

要求干净提交。原始输入、spec、编译trace、逐设计gzip与逐次完成journal都保留；
若任务中断，完成journal提供明确范围，但不能把不完整run写成完成的48次实验。
