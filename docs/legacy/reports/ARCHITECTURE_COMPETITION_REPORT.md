# 固定 H/plus：home、k2、k3 的公平架构竞争

2026-10-07；实验源码 `806fe829dacf4b02c9d0f1a100089e2f135cf613`；服务器 eex005。

**结论：三种结构都有自己的 Pareto 区域。k2 在低存储、低布线预算下有优势；k3 用更多接口和布线换取更高服务。固定 lane 和 buffer 上限，只改变 wire 上限，就能翻转随机负载下的胜者。**

工程整理已结束。本轮直接完成了注册设计族内的布局、接口和方向选择，未增加 placement、真实 workload 或新仲裁研究。所有性能来自同一个完整字执行与固定字节 Service LP，成本来自同一个 `CostModel`。

## 1. 公平比较了什么

固定 H/plus、36C+36M、32 banks/M、256-bit/native slot、always-ready 原生源、相同逻辑数据与 controller。所有设计满载和部分活动都保留每活动 compute 至少 1 TB/s。各架构独立建立合法静态布局，设计阶段完成后冻结；k2 没有复用 k3 的布局。

- Home：全本地，保住原生服务的最低实现。
- k2：每 bank 为 home 加一个 shared，比较两个二方向分组和一个四方向分组；真实边缘保留 private banks。均衡分组采用最小线长指派。
- k3：每 bank 为 home 加两个相反 shared，比较两组方向；按活动分布求最大权匹配，并保留最大基数匹配对照。允许未配对 compute 保持全本地。
- 位宽为 32–256 bit、步长 32；由完整字容量决定必要的 D1/D2，剔除没有容量增益的深度。每种结构都包含 256-bit direct 强基线。
- 每个接口的静态 home 比例由实际单出口能力反推，再用并发完整字执行验证。不是沿用手选的 50/50，也不是直接把宽度比例当服务。

两个 workload 分开优化、分开评分：均匀 random9 的精确 9-of-36 期望；clustered9 为 6×6 索引内全部 16 个不回绕的 3×3 窗口。二者是已知设计分布；另报告冻结设计的交叉表现。没有对每个活动样本重新布局。

“优化完成”覆盖[预先注册的结构化设计族](../methods/ARCHITECTURE_COMPETITION.md)：互惠条带、均衡 bank 分组、同角色接口和指定方向图。它不覆盖任意非互惠布局、逐 bank 非均匀模板或全 fabric 的全局最优。

## 2. 从第一性约束分开收益来源

令两个角色的完整字独占服务为 qH、qS，静态 home 比例为 λ。固定字节要求：

\[
\gamma\le\min(q_H/\lambda,q_S/(1-\lambda))\le q_H+q_S.
\]

取 λ=qH/(qH+qS)，并验证并发满载服务为 1，即达到该接口的独占上界。本轮全部 161 个可行候选都闭合了这个界，没有比例优化失败却被按乐观容量计分的候选。

在本轮固定发起配额下，客户端有必需共享伙伴活动时得到 1；全部必需伙伴空闲时得到 γ。因而平均服务可写成：

\[
\bar r=1+G(\gamma-1).
\]

这里 **γ 由接口执行和数据比例决定；G 由数据依赖的伙伴集合、边界和活动分布决定；成本由制造的完整模板决定。** 三者不再混成一个“sharing 倍数”。该式描述注册周期配额的服务见证，不是任意动态调度的容量区域。

| 结构/冻结布局 | 配对数 | 带 private bank 的 compute 数 | G：random9 | G：clustered9 |
|---|---:|---:|---:|---:|
| home | 0 | 36 | 0 | 0 |
| k2，方向 2/3 | — | 16 | 0.327731 | 0.083333 |
| k2，方向 1/4 | — | 16 | 0.327731 | 0.041667 |
| k2，四方向 | — | 16 | 0.186211 | 0 |
| k3，方向 2/3，random 优化 | 18 | 0 | 0.771429 | 0.333333 |
| k3，方向 1/4，cluster 优化 | 15 | 6 | 0.642857 | 0.472222 |

k2 的边界限制有物理来源：满载总需求等于总原生服务，因此每个 bank 都必须贡献。某份必要字节只能由 private bank 提供时，拥有它的 compute 无法随伙伴空闲一起加速。其余 compute 的对象跨多个 bank 组，额外服务要求多个必需邻居共同空闲。k3 用更高模板成本将整份对象的共享依赖集中到一个伙伴。

增加方向也可能减小 G：四方向 k2 的接线较短，但当前 clustered 分布下没有增益。这说明方向数本身不能预测有效服务。

## 3. 性能与成本前沿

以下为 random9 的代表点。服务单位 TB/s/active compute；全部满载每 C 为 1。成本按**每个 memory 的完整重复模板**计入，包含当次实例不用的方向。

| 设计 | Home/shared/shared | Home 比例 | 平均服务 | Lane bits | Endpoint 存储 bits | 接入 wire bit-mm |
|---|---|---:|---:|---:|---:|---:|
| home direct | 256/—/— | 1 | 1.000000 | 8,192 | 8,192 | 120,832.0 |
| k2 direct，方向 2/3 | 每 bank 256/256 | 1/2 | 1.327731 | 16,384 | 8,192 | 241,561.6 |
| k2 direct，四方向分组 | 每 bank 256/256 | 1/2 | 1.186211 | 16,384 | 8,192 | 214,681.6 |
| k3 A，D=(1,1,1) | 256/128/128 | 2/3 | 1.385714 | 16,384 | 24,576 | 297,497.6 |
| k3 B，D=(1,2,2) | 256/160/160 | 8/13 | 1.482143 | 18,432 | 40,960 | 341,664.0 |
| k3 direct | 256/256/256 | 1/2 | 1.771429 | 24,576 | 8,192 | 474,163.2 |

Direct 计每 bank 一个共用完整字寄存器，故 D=0 不表示存储为零。Buffered 计各制造出口的完整字队列。Pipeline 和控制另列，未混入 endpoint storage。

相对公平的 **k2 direct** 强基线：

- A：服务 +4.37%，lane 不变，endpoint 存储为 3 倍，wire +23.16%。
- B：服务 +11.63%，lane +12.5%，endpoint 存储为 5 倍，wire +41.44%。

因此，A/B 相对旧等宽 k3 的改进不能自动解释为对 k2 的全面优势。

自动搜索还找到 **160/256/256、D=(2,1,1)、λ=5/13**：同样达到 1.482143，使用 21,504 lane bits、32,768 endpoint bits、428,851.2 wire bit-mm。它比 B 少用 endpoint 存储，却多用 lane 与线。由此可见，“优先加宽 home”是 lane 成本目标下的结论，不能替代多成本 Pareto 综合。

随机分布的主前沿保留 35 个命名设计，对应 26 个不同的性能/成本点；其中部分方向/布局在随机分布下并列。Cluster 主前沿为 17 个点。两种 workload 的全局前沿均保留 home、k2 和 k3。

![执行性能与三项成本的前沿投影](../../artifacts/figures/architecture_competition/frontier.svg)

图中每个点是在四维目标中非支配的设计；二维投影中的重叠或表面支配不代表四维支配。[可下载 PDF](../../artifacts/figures/architecture_competition/frontier.pdf)。

## 4. 相同预算下，谁值得

各结构在同一个预算盒内独立选择自己的最佳可行设计。下表为 random9：

| Lane 上限 | Endpoint bits 上限 | Wire bit-mm 上限 | home 最优 | k2 最优 | k3 最优 | 胜者 |
|---:|---:|---:|---:|---:|---:|---|
| 16,384 | 8,192 | 245,000 | 1.000000 | 1.327731 | 不可行 | k2 |
| 16,384 | 24,576 | 300,000 | 1.000000 | 1.327731 | 1.385714 | k3 A |
| 18,432 | 49,152 | 245,000 | 1.000000 | 1.327731 | 1.192857 | k2 |
| 18,432 | 49,152 | 350,000 | 1.000000 | 1.327731 | 1.482143 | k3 B |
| 24,576 | 8,192 | 480,000 | 1.000000 | 1.327731 | 1.771429 | k3 direct |

第三、四行只改变 wire 预算，胜者就翻转。强 sharing 是否值得，不能在不计接入线成本的条件下作答。

相同服务目标也给出清楚选择：random9 目标 1.3 时，k2 direct 在本目录内同时最低 lane、endpoint 存储和 wire；目标 1.4 已超过当前 k2 族的 1.327731 上限，需要 k3 或新的结构。达到 1.4 的成本前沿仍包含 B、反向宽度方案和宽 direct，不能先压成一个没有校准权重的“总面积”。

完整输出包括 240 个 workload/预算盒的选择，以及[同服务目标成本表](../../artifacts/results/endpoint/architecture_competition_service_targets.csv)。

## 5. 布局确实随 workload 改变，但测试时冻结

在同一个 B 接口和相同硬件成本下：

| 冻结布局 | random9 | clustered9 |
|---|---:|---:|
| random 优化：方向 2/3，18 对 | 1.482143 | 1.208333 |
| cluster 优化：方向 1/4，15 对 | 1.401786 | 1.295139 |

Cluster 优化接受少配三对，以换取该分布下更有价值的空闲伙伴。这是静态伙伴选择的收益，未改变 H/plus placement，也未增加接口预算。对应宽 direct 的 cluster 服务达到 1.472222；k2 最好为 1.083333。

这里的交叉评估表明选择依赖活动分布，没有声称一个设计对所有分布最优。真实 MoE/LLM trace 仍属于后续阶段。

## 6. 统一账本中的其他代价

主前沿采用 bank 端 serializer。以下量在全部候选中单独保存，并计算扩展成本前沿：

| 设计 | Bank-port 边 | Pipeline bits | 控制存储 proxy bits | 配置 HB signal bits |
|---|---:|---:|---:|---:|
| home direct | 32 | 63,488 | 96 | 8,000 |
| k2 direct，方向 2/3 | 64 | 126,976 | 224 | 16,000 |
| k3 A | 96 | 155,904 | 352 | 24,000 |
| k3 B | 96 | 179,008 | 1,376 | 24,000 |
| k3 direct | 96 | 248,320 | 224 | 24,000 |

Pipeline 按每 2 mm 一个寄存级的统一 proxy 计算，没有时序收敛或链路延迟仿真。控制为固定序列 ROM/游标的显式代理。Bank 出口位宽、HB 配置位宽和 endpoint 存储没有互相替代。

若 serializer 放在 port 端，则此前长线仍为 256 bit；k3 A/B 的 wire 都回到 474,163.2 bit-mm。归档保留这种敏感性的独立前沿：random 为 41 个命名设计、cluster 为 21 个。它不能与 bank 端结果混为同一硬件实现。本地 selector 接线长度尚未知，未用零冒充测量值；这些资源计数不能直接换算为面积或能耗百分比。

## 7. 验证与复现

- 生成 657 个组合；原生并发能力不足剔除 256 个，private bank 的 home 保底不满足剔除 240 个，保留 161 个。
- 缓存 63 份局部周期完整字见证；逐槽守恒、队列容量与首尾状态重复。所有可行接口的比例界都闭合。
- 各结构前沿、全局主/扩展前沿、serializer 敏感性前沿及预算胜者共选出 60 个命名设计，去除 6 个完全相同的布局/接口别名后，验证 **54 个实际设计**。
- 每个设计回放 full、single、one_pair、一个注册 random9、first9、16 个 cluster，共 21 场景；每场景执行吞吐、公共完成及流体上界 LP，共 **3,402 个 LP**。流体值只作上界，不进入执行排名。
- 随机期望通过每个 compute 的实际必需伙伴邻域做精确组合计数；不枚举全部 9-of-36 集合，也不拿单个 seed 均值替代精确期望。
- 系数公式与公共执行器最大差 **4.44×10⁻¹⁶**；完整字节资源见证最大残差 **6.28×10⁻¹⁵**。下游组合按所有常驻出口峰值相加验证，无超配。
- **18 项相关测试通过**，含比例闭合、k2 direct 强基线、不同方向/部分配对合法布局。前轮已做的历史全套与等价回归保留原记录，本轮未重复声称全部重跑。

原始结果保存吞吐、common completion、每 C 速率、流体上界、LP 残差、配置、布局哈希和周期状态。公共完成没有作为本轮新增优化目标；也没有将平均带宽倒数解释成平均任务时间。

在 eex005 干净源码提交运行：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python -m unittest tests.test_design_contracts tests.test_role_interface_regression -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python -m w2w run_architecture_competition --output memory_results/architecture_competition/results.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python -m w2w.visualization.render_architecture_competition artifacts/results/endpoint/architecture_competition.json.gz --output memory_results/architecture_competition/frontier
```

实验用时约 116 s；图由后续仅可视化提交 `2001a78` 生成。原始实验 commit、注册协议哈希与数据未因报告或绘图修改而重写。

- [完整压缩结果](../../artifacts/results/endpoint/architecture_competition.json.gz)
- [全局主前沿 CSV](../../artifacts/results/endpoint/architecture_competition_frontier.csv)
- [溯源、字节哈希与审计](../../artifacts/provenance/architecture_competition_manifest.json)
- [18 项测试日志](../../artifacts/provenance/architecture_competition_tests.log.gz)

## 8. 下一研究动作

本轮证明有必要保留 k2/k3 两条路线，再做有成本约束的逆向综合。固定当前 placement，从目标平均服务 t 和结构活动系数 G 反推：

\[
\gamma_{\mathrm{required}}=1+(t-1)/G,\quad G>0.
\]

先用 γ≤2 与制造成本界淘汰不可能的结构，再由实际完整字容量合成宽度/深度和静态比例，输出达到目标的非支配成本实现。本轮自动目录已经是这个方法的有限实例；下一步应比较逆向筛选与本轮精确目录的质量、执行次数，并尝试有明确成本收益的 k2 分组/非均匀接口扩展。

暂不释放 placement，不继续工程整理。等这种需求到实现的选择稳定，再让几何改变方向数和路径成本；真实 trace 放在更后面。
