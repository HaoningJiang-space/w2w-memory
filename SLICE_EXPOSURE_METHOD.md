# Striped exposure：先检查端点带宽语义

用户提出的 A partitioned / B striped / C full-pooling 是一个合理的最小对照。
本实验只检查服务包络；不启动 DSE，也不声称模拟了真实 LIO 电路。
[已完成的 108 次核验](SLICE_EXPOSURE_REPORT.md)。
其物理依据与未知项见 [bank→HB 边界](BANK_HB_PHYSICAL_BOUNDARY.md)。

## 先补上两个不同的容量约束

每个 memory reticle 32 banks，每 bank 4 个 slices/endpoints。令每 bank 服务为 μ=1/32 TB/s：

- 共享父资源：`sum_s flow[b,s] <= μ`，任何情况都保留。
- 每个端点：`flow[b,s] <= λ`，不能从“有四组地址”推断 λ。

两种假设分别比较，不混成一个结果：

| 模式 | λ | 含义 |
|---|---:|---|
| fixed_share | μ/4 | 每组有固定的四分之一原生服务上限 |
| elastic_bank | μ | 一个组可以消耗整 bank 的服务额度，但所有组总和仍不超过 μ |

第二种是待验证的硬件能力，不是公开 LIO taps/mux 文本已经证明的结论。
还必须核对 group 对应独立地址范围，还是一次读出中的部分数据位；后者需要
完整数据聚合，不能让不同 compute 各拿一部分就计成独立完成的请求。
本容量探针暂未约束地址或 word assembly，故只能作为包络。
两种模式的总 DRAM、HB 和 controller 相同，但端点配置能力不同；不能跨模式宣称等成本。

在每种模式内，仅改 wiring：A 每 bank 所有 slices 到它的 private port；
B 每 bank 的 slice s 到 port s；C 每 slice 可到所有 ports，作为乐观包络。
A/B 每 memory reticle 都有 128 条 endpoint-to-region 连接，C 为 512 条。
它们不是旧模型的 bank-port edge 数，也不代表相同 wirelength。

## 不依赖种子的两个推论

在 free byte assignment、均质 banks 和本接口容量模型下：

1. 固定 λ=μ/4 时，A 和 B 每个 port 都得到总计 1/4 TB/s 的独占资源；
   每 bank 的四个 slice 上限之和恰好是 μ，父约束不再额外耦合它们。
   因此二者可以收缩成相同的 port-capacity graph，对任意 active set 的最大总流相同。
2. 当 λ=μ 时，B 的每个 bank 对四个 ports 分别有一个足以承载 μ 的端点，
   所有端点共享同一个 μ 上限。其可行流集合等价于该 bank 可以自由路由到所有 ports。
   所以本容量包络中 B 等价于 C，而不是处在二者之间。

**因此，striped 是否有效首先取决于 λ 和 bank 内部可共享服务的含义。**
若 λ 介于两者之间，或数据地址驻留、行状态、控制归属进一步限制服务，才可能出现
中间结果。先核定这些含义，不把目标 1.7× 写进模型。

## 最小计算核验

保持 300 mm、36C+36M；同一 memory reticle 1 TB/s；四个 HB region 各 1 TB/s；
每 C controller 4 TB/s。沿用 Aligned / X / XY 的匹配几何和原 overlap fractions。
每个 bank、端点、memory port、HB link、compute port 和 controller 都单独限流。

三种 geometry × 两种端点语义 × 三种 wiring × 六个需求场景，共 108 次最大流：
同一个内部 compute 单活动、全活动，以及预先固定 seeds 9000–9003 的 9-of-36 活动。
没有训练、选优或调参。所有结果精确用 1/128 TB/s 整数流单位检查容量与流守恒。
这是一个连续容量 LP 的最大流实现；整数单位用于精确计数，不把它称为 ILP 架构综合。

**边界**：请求尚未绑定到固定 bank/slice 地址，结果是 free-placement 服务上界。
即使 B 在 elastic 模式下较高，也没有证明静态布局收益、可独立访问多行或新增吞吐的
物理实现。反之，fixed_share 模式 A=B 也不证明它们在所有固定地址/热点模式下等价。
本步不引入 DRAM timing、runtime migration 或 wafer-scale 搜索。

```sh
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest test_slice_exposure_probe
OPENBLAS_NUM_THREADS=1 .venv/bin/python slice_exposure_probe.py --output memory_results/slice_probe
```
