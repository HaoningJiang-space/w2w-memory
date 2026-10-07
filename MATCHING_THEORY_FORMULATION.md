# 深层原因与问题定义：固定数据的匹配混合

本说明只解释已有模型并定义优化问题，不增加架构机制或开展新的 placement 扫描。
实验依据为 `MATCHING_PLACEMENT_REPORT.md` 和提交 `2ad20db` 的原始结果。

## 1. 核心机制不是“资源可达”，而是固定字节流的资源互补性

设 compute c 的一个完整请求流，必须从 memory m 取比例 A[c,m] 的字节。
若服务速率为 r[c]，这部分字节的服务量必须为 A[c,m]·r[c]。
它不能因为另一个 memory 空闲而被替换，否则就改变了固定驻留语义。

因此，不同 memory 上的数据片段是完成请求所必需的互补资源，而不是随时可替换
的服务供给。单个必经 memory/HB 出现拥塞，就会限制整个流。相邻空闲带宽的总和，
以及无固定数据约束的 max-flow，都不足以刻画这种服务能力。

三个层次要区分：

1. 物理图 E：哪些 HB 路径存在；
2. 静态字节矩阵 A：每个流到底必须经过哪些 memory；
3. 活动集合 S 与服务目标：这些必经资源当前和谁竞争，是否允许牺牲某些流。

Matching support 约束 A 的可行性；capacity 和端口约束限制 A·r；需求的联合分布
决定“所有必经资源同时获得余量”的机会。Cycle 是其中一个受限模型的结构表征。

## 2. 满载平衡为什么导向 matching

当前模型有 N 个 C 和 N 个 M，每个 M 服务 μ=1，每个 C 的注册满载速率为 1。
每个流的字节比例满足 A≥0、Σ_m A[c,m]=1。满载约束要求 Σ_c A[c,m]≤1。
因为矩阵总和为 N，所有列和必须等于 1，A 是双随机矩阵。

Birkhoff–von Neumann 分解给出 A=Σ_k λ_k P_k，λ_k≥0、Σ_k λ_k=1，P_k 是
支持图中的 perfect matching 矩阵。唯一 matching 因而强制唯一满载平衡布局。
这是已有定理的应用，不是本工作的图论创新。

**但一个 perfect matching 不是完整的服务证书。** 本轮每条 HB 边只有 0.8 TB/s，
若只使用一个 matching，则每个 C 最多得到 0.8。混合两个 matching、各放一半字节，
每条边只需承担 0.5，才可能达到满载 1。实际证书还要检查 memory、controller、
两端 port 以及共享物理通道的容量。

所以方法不是“第一套 matching 保底，第二套负责加速”，而是“联合选择 matching
及其数据比例，让混合后的完整服务约束可行”。

该双随机结论依赖等资源、饱和满载、固定字节、无复制与无转发。其他条件对应更
一般的运输多面体，不应硬套 perfect matching。

## 3. Pair 为什么更容易释放完整请求的服务能力

先限定：两套边不相交 matching、50/50 字节比例、每 M 服务 1、每条 HB 容量 0.8、
每个 active C 至少服务 1、controller 不成为瓶颈。用 ℓ 表示交替环内的 compute 数，
实际二部图环长是 2ℓ；pair 是 ℓ=2，即四边交替环。

在一个 memory 上两个流各驻留一半字节，约束为：

\[
\tfrac12 r_i+\tfrac12 r_j\le1.
\]

若 i、j 都 active 且各自保底 1，它们都只能维持 1。若只有 i active，该 memory
可独占使用，但两条 HB 各承担一半字节，故 i 的独占速率是 γ=min(2,2×0.8,4)=1.6。

- Pair 中，一个 C 的两个 memory 都与同一个伙伴竞争。只需这个伙伴 idle。
- ℓ≥3 的环中，两个 memory 分别与两个不同邻居竞争。两个邻居必须同时 idle。

因此令 Γ_i 为与 i 共享必经 memory 的不同竞争 compute 集合，有：

\[
r_i=1+0.6\,\mathbf1\{\Gamma_i\cap S=\varnothing\},\qquad i\in S.
\]

Pair 的 |Γ_i|=1；所有 ℓ≥3 的环均为 |Γ_i|=2。竞争邻居“是否重复”才是这里的关键。
不是环越长就有越多直接竞争者，也不是一次请求会穿越整条环。

### 3.1 独立 Bernoulli 活动：pair 后是平台，不是持续下降

每个 C 独立地以概率 p active，条件在 i 已 active：

\[
\mathbb E[r_i\mid i\in S]=
\begin{cases}
1+0.6(1-p),&\ell=2,\\
1+0.6(1-p)^2,&\ell\ge3.
\end{cases}
\]

| p | Pair，ℓ=2 | 任意 ℓ≥3 |
|---|---:|---:|
| 0.10 | 1.5400 | 1.4860 |
| 0.25 | 1.4500 | 1.3375 |
| 0.50 | 1.3000 | 1.1500 |
| 1.00 | 1.0000 | 1.0000 |

这是“一个指定 active compute 的条件期望”，不是无条件单节点吞吐，也不要直接
替换成随机 active 数量下每个场景先除以 active 数量再取平均的指标。

### 3.2 当前实验是恰好 9-of-36，不是独立 p=0.25

条件在 i active，其余八个 active 从另外 35 个 C 中不放回选择：

\[
P(\text{一个伙伴 idle}\mid i\text{ active})=27/35,
\]
\[
P(\text{两个伙伴都 idle}\mid i\text{ active})=
\binom{33}{8}/\binom{35}{8}=\frac{27\cdot26}{35\cdot34}.
\]

所以精确期望为 pair 1.462857、任意 ℓ≥3 为 1.353950。20-seed 的 1.486667 是样本
均值，不能替代总体值。该模型预测的平均带宽—环长图应在 pair 后下降一次，然后平台。

### 3.3 公共完成能力依赖整张竞争图，也不必随环长单调

公共服务大于 1 的条件是 active 集合 S 在竞争图中构成独立集。设每个交替环含
ℓ_j 个 compute，I_ℓ(x) 是相应竞争环的独立集计数多项式：

\[
I_\ell(x)=1+\sum_{k=1}^{\lfloor\ell/2\rfloor}
\frac{\ell}{\ell-k}\binom{\ell-k}{k}x^k.
\]

对 ℓ=2，I_2(x)=1+2x，也适用。恰好 a 个 active 时：

\[
\mathbb E[r_{\rm common}]=1+0.6\,
\frac{[x^a]\prod_j I_{\ell_j}(x)}{\binom Na}.
\]

固定 N=36、a=9，将全部 C 分成等长交替环：

| 每环 compute 数 ℓ | 平均吞吐精确期望 | 公共带宽精确期望 |
|---|---:|---:|
| 2 | 1.462857 | 1.158652 |
| 3 | 1.353950 | 1.027598 |
| 4 | 1.353950 | 1.042181 |
| 6 | 1.353950 | 1.039885 |
| 36 | 1.353950 | 1.039827 |

这里 ℓ=4 的公共期望反而高于 ℓ=3，说明“越短越好”的泛化不成立。
现有实际 packed matching 是 ℓ={3,3,6,8,16}，其公共精确期望为 1.037702。
以上等长环是数学对照，不声称都能由当前 wafer 几何实现。

## 4. 保底与相关性为何不能从解释中删去

上述闭式速率使用了 active C 的最低服务为 1。若去掉保底，长环中连续三个 active
C 可从 (1,1,1) 改为 (1.6,0.4,1.6)，相邻约束仍满足，总吞吐从 3 到 3.6。
这在一个六 compute 环的独立 LP 中已直接验证。代价是中间 C 的服务下降。

所以“竞争伙伴 active 就不能加速”不是一般 memory 定律，而是固定布局、当前容量
以及保底目标共同决定的结果。放松保底后需要重新求服务优化，不能继续套同一概率式。

非独立 activity 时，正确对象是
P(Γ_i∩S=∅ | i∈S)，不能只看 p 或两两 Pearson correlation。存在两个以上伙伴时，
两两统计通常不能完整决定这个联合事件。物理上可用的短环若把经常同忙的 C 绑定，
可能不如具有更好需求互补性或更强 HB 容量的另一构造。

## 5. Edge capacity 为什么与数据比例共同决定收益

考虑一个对称 pair，home HB 容量 H、cross HB 容量 S；两颗 memory 各 1。
每个 C 将 λ 字节放 home、1−λ 放 peer，两边使用同一个 λ 以保持满载列平衡。

满载 1 的必要边容量条件是 λ≤H、1−λ≤S，即
max(0,1−S)≤λ≤min(1,H)。独占服务上界为：

\[
\gamma(\lambda)=\min\left\{4,\frac1\lambda,\frac1{1-\lambda},
\frac H\lambda,\frac S{1-\lambda}\right\}.
\]

取 H,S≤1 且没有其他共享通道瓶颈，最佳比例 λ*=H/(H+S)，γ*=H+S；
满载保底 1 还要求 H+S≥1。这是本轮对称 pair 的解析结果，不是一般异构环公式。

H=0.8，S 从 0.8→0.6→0.4→0.2 时，λ* 从 1/2→4/7→2/3→4/5，
独占速率从 1.6→1.4→1.2→1.0。由此直接解释四个相同 support 图的性能变化。

两个 matching 的不同交替环还可以使用不同 λ_j。全 wafer 统一的 λ 只是一个
受限候选，不是所有平衡布局。在同一交替环内，列和约束则会迫使相应 λ 一致。
不同环的 λ 不同时，support 仍是两套 matching 的并集，但 A 一般不能仅用这
两套全局 matching 加一个统一系数表示；其全局凸分解可能需要更多 matching。
因此应区分“两 matching 的 support”和“仅两个全局 matching 的凸组合”。

## 6. 完整的研究问题：设计阶段固定布局，场景阶段只分配服务

输入：

- 有限合法 placement 集合 G，每个 g 使用统一重复模板并满足面积/wafer 约束；
- 由 g 得到的实际 HB 边集合 H_g；一条边 e 带有 c(e)、m(e)、两端 port 和容量 b_e；
- 固定 port 容量 q、memory 服务 μ、controller 上限 κ 与存储容量 K；
- 训练场景 w 的概率 π_w、需求 d_cw 和注册最低服务 h_cw。

本阶段固定 HB provisioning，不引入新电路。每个对象使用同一 A 条带比例，因此 A
同时描述固定字节份额和数据占用。更一般的对象访问分布需要对象级布局与场景字节
份额，不能将本模型直接当作任意热点模型。

设计变量：g；静态字节矩阵 A；用于“两 matching”受限空间的二元 z_cm。
z 表示某条 C–M 邻接是否被静态数据使用，不是允许每个 reticle 单独制造不同 bank mask。
底层 pooled memory 接口目前仍是统一的放松假设。

布局约束：

\[
A_{cm}\ge0,\quad \sum_m A_{cm}=1,\quad
A_{cm}\le z_{cm},\quad z_{cm}\le\mathbf1\{(c,m)\in E_g\},
\]
\[
z_{cm}\in\{0,1\},\qquad
\sum_mz_{cm}\le2,\quad\sum_cz_{cm}\le2,
\qquad \sum_c V_c A_{cm}\le K_m.
\]

在当前等资源满载目标下，再要求 Σ_c A_cm=1，并为 full-load 场景检查下述所有
物理约束。平衡布局的正权重 support 在最大 degree 2 时由交替环与孤立 C–M 边构成，
其 support 可由两套 matching 覆盖；A 允许分环比例，含义如上一节所述。
z 上没有实际字节的装饰边不算有效 support。
若只研究两套边不相交 matching，可把 z 两侧 degree 固定为 2。

固定设计 (g,A) 后，每个场景的服务子问题变量为 r_cw 与 HB flow f_ew：

\[
\sum_{e:c(e)=c,m(e)=m}f_{ew}=A_{cm}r_{cw},
\]
\[
0\le f_{ew}\le b_e,\qquad
\sum_{e:m(e)=m}f_{ew}\le\mu_m,
\]
\[
\sum_{e\text{ incident on port }p}f_{ew}\le q_p,
\qquad h_{cw}\le r_{cw}\le\min(d_{cw},\kappa_c).
\]

inactive C 的 d=h=0。若使用共享内部通道，还需加入对应的 flow 容量约束，不能只
用独立 b_cm 表示共享物理瓶颈。满载证书以所有 r_c=1 代入验证；删除需求后可沿用
剩余 flow，故任意子集仍可行。

定义服务价值：

\[
\Phi(g,A;w)=\max_{r,f}\frac{\sum_{c\in S_w}r_{cw}}{|S_w|}.
\]

设计问题为：

\[
\boxed{\max_{g,z,A}\ \sum_w\pi_w\Phi(g,A;w)}
\]

受上述静态、物理和预算约束。若研究系统总吞吐，去掉 |S_w|；若研究同步阶段，
改用公共完成目标，例如 r_cw≥t_w D_cw、最大化 t_w，其中 D 是阶段工作字节量。
这些目标不应混用。保底 h 可取 1、0.95 或其他注册值，不是永远固定为 1。

在这个定义中，capacity-weighted matching flexibility 不是一个脱离 workload
的边计数。可操作的定义是：在相同资源和服务目标下，合法匹配混合所能达到的
最优期望服务值，或它相对于明确基线的增益。Cycle/count 等指标用于解释这个值。

## 7. 最小可解版本：带权 reciprocal pairing

暂时固定 g 和一套 home 匹配，把节点重新编号为 C_i↔M_i。只考虑 reciprocal
候选 {i,j}：两条 home 和两条 cross 边都必须存在，并且至少有一个 λ 能通过 full
load 证书。对每个候选 pair，用实际容量算单边活动时的 γ_i(λ)、γ_j(λ)。

若目标是总吞吐，相对于 active C 各服务 1，该 pair 的训练增益为：

\[
\Delta_{ij}(\lambda)=\sum_w\pi_w\big[
\mathbf1\{i\in S_w,j\notin S_w\}(\gamma_i-1)+
\mathbf1\{j\in S_w,i\notin S_w\}(\gamma_j-1)\big].
\]

若目标是前述场景平均每 active C 带宽，每项还要除以 |S_w|。用训练数据选 λ，
得到 Δ*_ij，然后求：

\[
\max_t\sum_{\{i,j\}}\Delta^*_{ij}t_{ij},\qquad
\sum_{j:\{i,j\}\text{ eligible}}t_{ij}=1,\quad t_{ij}\in\{0,1\}.
\]

这是最大权 perfect matching，pair 图通常不是二部图。每个 C 只进入一个 pair，
在当前 reticle 服务模型中各 pair 的 memory/port 资源不相交，因此增益可加。
如果 home 单独可以保底，可允许未配对节点，把等式改为 ≤1；本轮 home 只有 0.8，
不能在维持保底 1 时悄悄允许 singleton。

这个问题已经把物理容量、静态比例、活动互补性结合起来，不需要运行时搬数据。
它是受限 pair 家族的可解起点，不证明 pair 比所有长环、多 matching 或更高 degree
结构都好。若共享内部通道、bank 暴露或重复 mask 引入跨 pair 耦合，增益不能再简单
相加，必须回到更完整的服务模型。

## 8. LP、ILP 与 Gurobi 的边界

- 固定 g,A 后，A·r 中 A 是常数，服务子问题是连续 LP。
- 联合优化 A 和 r 时，A·r 是双线性项；再加入 g,z，就是混合整数非线性设计问题，
  不能因为用了 Gurobi 就称为 ILP/MILP。
- 有限枚举 placement、matching 和比例，再对每个设计求 LP，是可复现的受限搜索，
  不能称为全局最优连续联合综合。
- 上一节预计算 Δ 后，只有 t 是二元变量，是真正的 0–1 ILP，也可用组合匹配算法。
  一般 pair 图的 degree 约束 LP 放松可能产生奇环上的 1/2 分数解；不能删除整数约束
  就声称仍然得到合法 pairing。二部 C–M matching 的标准 LP 则有不同的整性性质。

当前 eex005 上的 Gurobi 受限许可证可以支撑这样的小规模 pairing ILP；更大的
设计模型仍须检查许可证规模，不能推断已有无限制学术授权。

## 9. 结论边界

可以主张：固定数据请求需要一整组资源同时可用；匹配结构控制资源重合方式，
物理容量与混合比例控制独占上限，需求联合分布决定释放机会。

不能主张：cycle 越短总是越好；两个 matching 自动保证满载；已有两个 matching
就实现了廉价 k=2 bank fabric；这些 reticle-level 数字已经是应用加速或 PPA 收益。

数学来源：[perfect matching / Birkhoff–von Neumann 分解算法](https://arxiv.org/abs/0909.3346)。
几何来源：[上游 H/plus，§4.2](https://arxiv.org/html/2603.05266v1)。
概率式、cycle 计数应用及本模型的优化定义在本说明中展开；不作为新的基础图论结论。

复核：运行 `.venv/bin/python verify_matching_theory.py`，对含 2、3、4、6 个 compute
的抽象环穷举全部非空活动集合，通过服务 LP 计算独立活动下的条件期望，并与公式
比较；另外穷举独立集计数，验证去除保底的反例。结果保存在
`matching_theory_checks.json`。这些是本地数学核对，不是新增 eex005 架构扫描。
