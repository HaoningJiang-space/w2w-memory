# 下一版设计：完整路径合同与共同完成感知的静态组织

2026-10-08。基于`dc57f76`的166次回放，新增数学分析和一个训练侧映射探针。
当前判断是：继续保留bank并行度，通过完整路径的状态分工和cohort感知的owner选择，
提高既有接口的价值。跨bank engine pool还不是本轮结果要求的改动。

## 1. 首先修正一个硬件推论：RX3不等于必须制造三个整字RX

[上一轮](RETURN_PATH_PROVISIONING_REPORT.md)的数字仍成立，但它们属于一个具体合同：
`read_replay`从字的第一bit发出时预留RX entry，直到最后一拍经过link并交付才释放。
RX2/RX3表示整个区间内可预留的完整字数量；每entry乘256得到的是明确声明的payload代理。

现有[RTL](../../rtl/endpoint_link.sv)采用另一种合同：

- TX整字FIFO后有一个独立的held-beat寄存器。
- HB传递带有效单位数的beat，RX根据实际接收的单位重组成完整字。
- RX同周期可以交付一字并接受新beat；其payload容量为256+W−gcd(256,W)。
- 现有roundtrip没有长线传播或反压往返，不能直接代替系统中的link=1。

| Shared W | 整字预留模型的满宽平均占位，L=1 | 当前RTL Shared reservoir |
|---:|---:|---:|
| 128 | 1.5 words | 256 bits |
| 160 | 2.125 words | 384 bits |
| 192 | 2.25 words | 384 bits |
| 256 | 2 words | 256 bits |

因此“160/192必须增加到三个完整RX字”不是硬件定理。
既有RTL已经在零链路延迟下分别恢复5/8、3/4 word/cycle，见
[roundtrip报告](ENDPOINT_ROUNDTRIP_REPORT.md)。现阶段应把系统预留状态和实际payload
的存放位置接起来，而不是将768-bit RX当成192-bit接口唯一可能的实现。

更好的具体候选是：保留现有bank-local TX和beat reservoir，在合法HB路径上显式插入
可反压的流水级，并分别记录以下状态：

1. 原生返回尚未序列化的完整字；
2. TX held beat和链路中的在途beats；
3. RX部分字与等待compute接受的完整字；
4. 保证不可撤销返回有存放位置的credit/metadata。

按现有局部声明，B和C的TX整字payload都为768 bit、三个RX总payload都为1024 bit；
可配置TX held-beat为416/448 bit，局部合计2208/2240 bit。
这个32-bit差值不包含新增HB流水、ready路径、控制和长线，不能取代完整成本。
它说明先使用已有reservoir并显式补齐链路，是比统一增加整字RX更值得验证的候选。

Elastic pipeline是已有方法，不作为本工作的独立创新；已有理论也区分功能对延迟的
适应性与吞吐是否保持。[Carloni等，TCAD 2001](https://sld.cs.columbia.edu/pubs/carloni_tcad01_lip.pdf)
本工作的设计问题在于：重复模板的哪些路径需要多少状态，静态驻留怎样让这些路径
共同满足目标服务，以及计入这些状态后哪种有限共享值得制造。

如果暂时保留原整字预留合同，一个简单的中间方案是Home用RX2、Shared用RX3。
每M的RX payload代理从32×3×3×256=73728降到32×(2+3+3)×256=65536 bit。
这需要回放层支持分角色深度，尚未实现；不能直接将旧RX3的任务时间写给它。

## 2. 用“总工作量＋不均衡”替代简单的活动相关性

设互惠pair中的两个compute需读取x、y个等大对象，Home比例λ≥1/2。
若路径容量与比例匹配、请求容量足够，两个memory的归一化原生工作量为：

\[
v_i=\lambda x+(1-\lambda)y,\quad
v_j=(1-\lambda)x+\lambda y.
\]

于是该pair的流体共同完成评分为：

\[
\boxed{t_{ij}=\max(v_i,v_j)=\frac{x+y}{2}
+\left(\lambda-\frac12\right)|x-y|}.
\]

Home-only为(x+y)/2+|x−y|/2；C的λ=4/7使不均衡项系数变成1/14。
共享并没有降低这对memory必须完成的总字节，而是使请求不均衡付出的代价变小。

这给静态组织两个清楚目标：

- 每个compute内，减少常一起读取的对象挤在一起。
- 每个pair内，控制窗口总工作量，同时让两端不均衡能被已配置的Shared能力吸收。

第二项不是单独最小化correlation。把大量任务集中到一个compute、把伙伴闲置，
可能扩大“可借带宽”，却让任务整体更慢；必须比较整个cohort最后一个必要资源。

一般结构用固定资源矩阵R表达，owner决定每窗口负载向量d_w：

\[
J(\pi)=E_w\left[\max_\rho (d_w(\pi)^T R)_\rho\right].
\]

本轮R包含每bank原生总量、每出口隔离周期能力、最短请求占位。
它是连续整对象的选型评分，忽略有限尾部、release/DAG和实际DRAM命令；不作为实测时间。
Home/k2/C/宽k3各自使用自己的合法资源矩阵，也各自选择自己的静态owner。

## 3. 已实现的训练探针

只读取已有64个训练请求的layer0、全部128个decode steps。
batch1/4/16形成10752个冷读cohort，三个batch大小等权。
没有读取之前48个测试请求或新增held-out完成时间。

四种结构固定H/plus、伙伴、N192和RX3合同。
各自从modulo与旧边际LPT中按自己的J选择起点，固定seed8109，每轮抽取256个expert
交换候选、接受最佳改善，执行8轮。所有交换保留每compute的常驻专家数量。
这是有限搜索，既没有任意布局优化，也没有全局最优声明。

| 固定结构 | 边际LPT评分 | cohort交换后 | 评分下降 |
|---|---:|---:|---:|
| Home | 2.343140 | 2.228312 | 4.90% |
| k2 | 2.232259 | 2.097392 | 6.04% |
| 宽k3 | 1.920471 | 1.771322 | 7.77% |
| C，λ=4/7 | 1.978016 | 1.834961 | 7.23% |

执行源码`9f647c8`，eex005，16.43秒。四组各接受8次交换。
当前结果只证明训练目标可以在固定容量下改善，不能写成应用加速或测试泛化。
完整交叉表也保留了不同搜索起点/目标之间的差异；例如C的映射在宽k3上的评分
1.770976略好于宽k3自身此次有限搜索的1.771322，说明搜索尚未收敛到全局最优。

## 4. 一个新的约束：对象级任意条带与普遍满载保底不兼容

“热对象全本地、冷对象放peer”看起来值得尝试，但需要先明确其保证范围。
考虑n个compute、n颗单位原生容量memory，每个compute可能独立选择自己的任意对象。
令a_com表示对象o在memory m的必需字节比例，每行和为1、没有副本或可替代来源。

要求任意满载对象组合都支持每compute单位服务，必要条件是每个m满足：

\[
\sum_c\max_o a_{com}\le1.
\]

对m求和，右侧为n；左侧中每个compute的Σ_m max_o a_com至少为1，因此必须全部取等号。
任取一个对象o，其各分量不超过这些max，且和同为1，故每个分量都必须等于max。
得到：

\[
\boxed{\text{同一compute的所有对象必须具有相同的memory字节分布。}}
\]

这是无原生余量、独立任意对象组合条件下的必要结论；出口和请求容量还有额外限制。
具体pair例子：两侧都混合“全本地”与λ=4/7条带对象。
当一侧读本地对象、另一侧读条带对象，某memory负载为1+3/7=10/7。
要覆盖任意这种选择，统一服务上限降到7/10，不能同时承诺每compute原生1。

因此更好的第一版设计是：保持经容量匹配的统一条带，优先改对象owner和伙伴。
若以后引入对象级不同条带，则应显式增加原生余量，或把保证范围限定为指定的联合
需求集合；不能继续沿用任意满载1的保证。固定地址的不同子区间仍可能产生不同访问比例，
此时应针对实际阶段需求重新核验保证范围。

## 5. 建议推进顺序与贡献定位

第一步，把现有beat-reservoir与显式HB流水接入统一系统合同，公平计费pipeline、RX
及credit。它解决“系统模型选出的容量对应什么硬件”，复用已有RTL，不另起FIFO课题。

并行完成cohort owner的训练/冻结/新请求回放。先固定伙伴，Home/k2/C/宽k3各自得到
同等搜索预算；再只增加一次合法伙伴交换，量出owner和partner各自贡献。
只有完整任务确实受跨bank共享engine数量限制，才继续研究pool的粒度。

专家共同激活和分离co-active experts已有明确研究，不能把采用cohort单独当成新颖性。
[Patterns behind Chaos，§III-C](https://arxiv.org/html/2510.05497v4#S3.SS3)
当前可以争取的贡献是：**用实际服务资源与重复模板成本决定数据组织，并给出可以保留的
运行时共享能力、必要状态和保证范围。** 上述工作量公式、满载约束和完整路径合同把
这一原则变成了可实现、可检验的设计选择。

## 6. 代码、合并与复现

- 纯推导：[theory/cohort_service.py](../../w2w/theory/cohort_service.py)。
- 固定硬件映射：[synthesis/cohort_placement.py](../../w2w/synthesis/cohort_placement.py)。
- 注册和编排：[探针协议](../methods/COHORT_PLACEMENT_PROBE.md)、[runner](../../w2w/experiments/probe_cohort_placement.py)。
- 独立逐交换重建：[validation/cohort_placement.py](../../w2w/validation/cohort_placement.py)。

`b4b8ce6`已在本轮起点`dc57f76`的祖先链中；无需重复合并。
过程中又收到`4dc61f8`、`5d6710a`的可选DRAM后端/桥接代码，已无冲突合入`eb1f6a8`。
本轮没有修改这些代码、编译桥接原生库或重跑旧性能结果。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m w2w.experiments.probe_cohort_placement \
  --output memory_results/cohort_probe.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m w2w.validation.cohort_placement \
  --source memory_results/cohort_probe.json --output memory_results/cohort_audit.json
```

合并后45项测试中42项通过、3项原生桥接集成测试因未配置库而跳过。
其中覆盖默认slot读回放、延迟完成/反压接口及新增7项理论/搜索测试。
独立审计重建32次接受交换和24个交叉评分，容量、输入SHA和注册参数一致。

[原始训练结果](../../artifacts/results/workload/cohort_design/probe.json.gz) ·
[交叉评分CSV](../../artifacts/results/workload/cohort_design/scores.csv) ·
[独立审计](../../artifacts/provenance/cohort_design/audit.json) ·
[溯源清单](../../artifacts/provenance/cohort_design/manifest.json)
