# 当前simulator的compute互联与执行边界

2026-10-08。对`447b512`之后的当前代码调用链与已发布81次回放做针对性核查。
独立探针源码`a3fe95b`在eex005执行；没有修改几何、调度或已有性能结果。

**结论：当前memory-service模型没有compute之间的通信网络。** 它提供直接C–M请求/返回，
既没有C–C直连，也不允许C–M–C转发。用于比较冻结数据的读完成时间可以保持此边界；
用于完整MoE/wafer应用时，这是必须补齐的架构缺口，不能将其开销设为零。

## 1. 实际执行的是哪个simulator

当前主实验调用链为：

`run_cohort_replay.execute → replay_reads → ReadResidency → CandidateEvaluator/DesignFabric`。

`contoured_geometry`生成36个H形compute和36个plus形memory；`MemoryFabric`只遍历
compute与memory之间的HB矩形交集。冻结Geometry的route类型固定为
`(compute, memory, compute_port, memory_port, overlap fractions)`。
`DesignFabric.paths`再将这些直接连接展开到可暴露bank，没有全图最短路径路由。

| 当前物理/服务项 | 本次核查 |
|---|---|
| Compute reticles / memory reticles | 36 / 36 |
| C–M物理端口连接 / 不重复C–M对 | 146 / 146 |
| C–C / M–M同层连接 | 0 / 0 |
| memory转发其他compute的流量 | 不支持 |
| C–M–C或C–M–C–M多跳通信 | 不支持 |
| Compute内部router队列、VC与仲裁 | 本执行器未建模 |

几何无向图有一个连通分量；例如C0–M0–C1存在两条相邻HB边。
但memory是`memory_endpoint`，不是端口间router，因此这不构成功能上的C0→C1路径。
`MemoryFabric.summary()`明确给出`forwarding_supported=False`。

上游代码仍包含RapidChiplet/BookSim，但当前实验没有调用它们。
`run_experiment.compute_results_for_single_system`对`memory_and_logic`请求BookSim或Orion
会直接拒绝。上游Logic-on-Logic的跨层网络也不能在替换成memory endpoint后自动保留。
Compute reticle的`central_router`标签不能代替当前执行器中没有实现的router行为。

## 2. 两个关于通信的最小反例

**非直接读被拒绝。** 在2C+2M fixture中删除C0–M1直接边，保留几何通路
C0–M0–C1–M1。仍让C0的一部分必需字节位于M1，构造读回放被拒绝，报`KeyError (0,1)`。
这验证当前执行没有偷偷通过C1转发，也没有把全图连通当成全局memory可达。
错误提示较底层，但没有接受非法读路径；本轮未为改善提示改写执行器。

**跨compute依赖只表示先后顺序。** 构造C0计算7槽、C1依赖C0再计算3槽，均无读请求。
即使memory link latency设为100，C1仍在第7槽开始，总完成10槽，发送bit数为零。
这是控制依赖的当前语义，不是一个有效的activation传输模拟。
`ReadTask`没有传输字节、通信源/目的、路由或网络完成事件；依赖满足即具备启动条件。

因此不能用`dependencies`或零时间join代表MoE token dispatch、expert output combine、
all-reduce、跨层activation传递或同步消息。最新45份输入trace的`compute_slots`全为零；
它们表示专家权重读取及join，不包含GEMM执行时间。

## 3. 其它直接相关的建模缺口

| 项目 | 当前行为 | 对使用结果的影响 |
|---|---|---|
| 请求网络 | 每compute注入配额、outstanding限制和固定request latency | 未计地址packet的HB带宽、路由排队或与返回争用；不能说请求网络已物理闭合 |
| 链路距离 | 所有路径使用配置的link latency；当前81次为1槽 | 延迟未由bank到HB线长/寄存级数自动生成，不能评价真实长线尾延迟 |
| HB/端口争用 | 预先叠加所有常驻出口峰值，拒绝超容量候选 | 是保守容量组合检查，不是共享router中的动态排队模拟 |
| DRAM供给 | 81次主实验为独立bank slot、native latency=0 | 结果受这个原生服务假设约束；HBM2探针另有共享通道和命令时序，预算不同 |
| Compute执行 | 每compute最多一个活动读任务；读后可加显式compute_slots | 没有GEMM资源、通信/计算重叠及cache模型；不能解释为完整GPU/LLM执行 |

第三个探针保持同一读和接口，仅将成本模型pipeline spacing从2mm改为0.5mm。
流水payload代理由768增加到2560 bits，读时间仍为4槽。它证实当前线长/寄存器计数与
回放链路时延没有自动连接；不能用成本表上的pipeline bits证明相应物理延迟已模拟。

## 4. 对现有结果与下一步的影响

当前有限共享并不需要compute先转发数据：C0的数据若合法驻留M1，就走M1→C0直接HB。
这条读路径的字节、source、RX和资源账本仍可独立验证。没有C–C网络，不会自动推翻
该读子阶段的81项结果，也没有证据表明这一缺失改变了已经公布的逐字计数。

但是，完整MoE需要token先到expert所在compute，输出再到下一消费者。改变expert owner
还可能改变这些通信路径和拥塞，因此**不能假定各布局遗漏相同开销、自然抵消**。
同理，之前最多0.0173%的资源下界差只约束读子模型，不证明整个wafer已经接近性能极限。

下一步首先明确compute通信的物理实现与其账本：

1. 如果采用logic wafer同层跨reticle网络，显式改变当前无同层连接假设，计入线、router和端口。
2. 如果保持只有跨wafer HB，则需要真实的端口间转发逻辑及路径；把它放在memory侧外围或
   其他logic层，是新的硬件与制造决定，不能让DRAM bank自动承担router功能。
3. 在确定的合法网络上，为任务加入activation/输出字节、源/目的和通信完成依赖。
   若与memory traffic共用资源，两类流量进入同一容量/队列账本；若独立，单独计制造成本。

先用一个producer→两个expert→consumer的小任务闭合通信、读与计算，再扩到同一份
冻结routing。暂不直接打开任意C–C连通或给所有dependency附一个常数，避免再次隐藏
数据位置与实际资源。当前可以继续做memory-service研究，但完整wafer系统的贡献还需要这一层。

## 证据与复现

[机器可读核验](../../artifacts/provenance/simulator_connectivity/audit.json)，
[执行日志](../../artifacts/provenance/simulator_connectivity/audit.log.gz)，
[32项相关测试](../../artifacts/provenance/simulator_connectivity/tests.log.gz)。
核验包括现有几何、非法间接路径拒绝、控制依赖语义和pipeline代理敏感性；不是整个仓库无bug证明。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m w2w audit_simulator_connectivity \
  --output build/connectivity_audit.json
python -m unittest tests.test_read_workload tests.test_memory_model -v
```

主要代码位置：`geometry/memory_model.py`、`domain/design.py`、`service/adapters.py`、
`service/read_replay.py`、`service/evaluator.py`、`workloads/read_trace.py`、`workloads/patterns_trace.py`。
