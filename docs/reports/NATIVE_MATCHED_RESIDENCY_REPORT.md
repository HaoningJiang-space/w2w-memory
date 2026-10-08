# 同一DRAM组织下，驻留比例应匹配实际原生供给

2026-10-08。保持B的256/160/160接口、D1/D2、方向、几何和请求预算不变，
将静态home比例从8/13改为1/2，完整对象读完成时间减少**17.44%**。
这是两次固定HBM2参考组织的单对象诊断，不是完整MoE batch或WoW工艺标定。

## 为什么运行这项对照

旧slot模型给每memory 32个独立机制bank，合计1 TB/s。其出口完整字能力支持B的8/13比例。
已接入的HBM2参考则让32 banks共享两个pseudochannels，通道峰值32 GB/s。
在本次单对象、跨两个memory的读中，Home和Shared各自的原生供给先成为限制。
因此原本合理的出口配比未必继续平衡两颗memory的必需字节。

在执行前注册了[协议](../methods/NATIVE_MATCHED_RESIDENCY_PROBE.md)：重放旧B作为原样对照，
再仅改变同一pair上的驻留比例与对应静态仲裁配额。若两颗memory的可持续服务相近，
1/2分配的条件时间预测为原来的13/16，即减少18.75%。该预测没有使用本轮计时结果。

## 固定条件与结果

读取同一份18,878,976-byte完整专家权重，共589,968个32-byte字，全部128个常驻专家保留。
同一owner、N192、RX2、request/native/link=1/0/1 slot；同一公开HBM2命令配置、桥接二进制、
FR-FCFS/open-row/refresh策略。端点槽为1.024 ns，原生命令周期为1 ns。

| 静态home比例 | 完成槽数 | 完成时间 μs | M8必需字 | M9必需字 | 两memory有效GB/s |
|---|---:|---:|---:|---:|---|
| 8/13 | 386,025 | 395.290 | 363,056 | 226,912 | 29.391 / 18.369 |
| 1/2 | 318,712 | 326.361 | 294,992 | 294,976 | 28.924 / 28.923 |

实际时间比0.825625，速度比约1.2112；与0.8125条件预测相近但不相等。
有限整字分配使1/2布局最后有16字差异；不能把流体预测写成逐字执行恒等式。
两条路径行命中率都约95.5%–96.0%，本轮最直接的变化是必需原生工作量更均衡。
我们没有单独归因余下预测误差，也没有由行命中率推出已经消除命令或返回背压。

原B逐字delivery hash、驻留hash、bank计数和完成时间复现旧归档。
两次回放均交付全部589,968字；独立审计核对每bank与36个controller计数、原生accept/serve、
最终pending=0、路径字节证书和完全相同的原生配置。没有通过减少数据或增加原生带宽获益。

## 设计判断

静态数据驻留应联合匹配**原生资源域、返回路径与请求预留**。同一接口在不同原生组织下，
合适的比例可以不同。这比单独扩宽Home或Shared更直接，也保留现有bank并行度。

在简化pair条件下，令两条独立来源的可持续速率为h、s，完成T字节的时间至少为
max(λT/h,(1−λ)T/s)；均衡点为λ=h/(h+s)。这里h、s必须包含真实原生约束，
并另行检验双方同时忙时的总供给与仲裁。它不是只把位宽代入的公式。

本次没有新增FIFO、跨bank互连、运行时迁移或伙伴切换。1/2驻留使静态配额表改变，
并未综合新的控制实现，不将配额缩短另报为面积收益。HBM2组织与旧slot资源不同，
本结果不进入81次cohort回放的架构排序。下一步应在同一个原生profile中检验多对象竞争，
而非把本例17.44%外推到整片wafer。

## 证据与复现

- 执行源码`a6003b32ebc343c71143878711e7cd2077d15de8`，hn072；两次原生执行合计约86.49 s。
- 独立核对源码`f44023fe29d810328ed3b2276795ea81a145046d`。
- [原始两次回放及manifest](../../artifacts/results/dram/native_residency/manifest.json)。
- [独立核对](../../artifacts/provenance/native_residency/native_residency_audit.json)；
  [执行日志](../../artifacts/provenance/native_residency/native_residency.log.gz)。
- 上游版本`72427a1bba3771564c4fb0e494ba02242fd1eaa7`。桥接SHA在每次结果中记录；
  原生库及动态链接位置在运行后核对，记录于同目录`library_check.log.gz`，不冒充运行中快照。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m w2w probe_native_residency \
  --output memory_results/native_residency_new
python -m w2w audit_native_residency \
  --source artifacts/results/dram/native_residency --output build/native_residency_audit.json
```

第一条命令需要已有`PYTHONPATH`和`W2W_RAMULATOR_BRIDGE`环境，见
[原生命令后端](../methods/DRAM_COMMAND_BRIDGE.md)。第二条不加载原生库、不重跑模拟。
