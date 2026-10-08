# 研究主线与当前证据

研究目标保持不变：在 repeated-reticle WoW Memory-on-Logic 中，联合配置服务接口、物理连接和静态数据驻留，使已有闲置 DRAM 服务能够被繁忙 compute 利用。

**当前最值得验证的是完整设计的收益与成本，而不是再增加一个 simulator 或接口机制。** 已有证据支持共享机会和静态方向复用，但尚未证明一个优于强基线的完整架构。新补的静态裁剪对照说明：configurable 的主要价值是以小幅 source 面积开销保留模板的方向选择能力，不能再把它描述成相对最佳固定实现节省三成面积。

## 哪些结果可以一起比较

| 比较 | 固定什么 | 能回答什么 | 当前结论 |
|---|---|---|---|
| Home、k2、wide k3、B/C 的同 owner 回放 | routing、几何、原生预算、固定逻辑对象 | 给定 owner 时，fabric/驻留配置有多少读阶段收益 | 已有66行同口径汇总，收益随窗口变化 |
| Home modulo 与 Home trained | 硬件，改变冻结 expert owner | 映射本身影响多大 | 两窗口 trained 更慢，其他窗口也有明显改善，不能只保留一侧 |
| Duplicated 与 configurable B | 位宽、选定方向、合法请求和服务 | 取消未用发送状态的代价 | 同服务；已有局部 P&R |
| Deployment-pruned 与 configurable B | 同库、位宽、合法方向与请求 | 保留方向选择要付出多少额外 source 硬件 | 本轮完成：configurable 比固定专用实现稍大 |
| C/RX3 模型与 B 的旧 RTL 面积 | 合同与状态组织不同 | 不能直接组合成同一设计的 Pareto 点 | C/RX3尚无对应完整物理成本 |
| HBM2 probe 与原 slot 模型 | 原生资源预算不同 | 只能检查参考时序影响与接口正确性 | 从本轮架构性能排序排除 |

wide k3 是固定 pair 的较宽参考，不是任意数据路由或 full pooling 的全局上界。Duplicated B 又是另一项同位宽、同布局的实现基线，不能把这两个“full”混成一项。

可复算账本：[ledger.json](../artifacts/results/research_evidence/ledger.json)与[66行对照](../artifacts/results/research_evidence/comparisons.csv)。全路径面积和应用加速未知项保持 null，不把 wire/bit proxy 换成面积。

## 静态裁剪强基线给出的新结论

将原 `endpoint_source` 的共享方向在综合前固定为 Left 或 Right，保持完整外部HB信号接口，并对错误目的地拒绝。分别从 duplicated 和 configurable 两种已有实现出发综合。后者也是消除无用方向逻辑的普通编译期特化，不增加新机制。

六个设计使用相同 Nangate45 typical 库、ABC 2000 ps 映射目标、驱动和负载。下表是 **source 综合面积**，不能和此前提取修复后的P&R数字混用。

| Source | 面积 μm² | Sequential cells | 制造后可选方向 |
|---|---:|---:|---|
| Duplicated | 17,265.528 | 1,879 | 两方向各有发送状态 |
| Configurable | 11,123.854 | 1,197 | Left或Right，部署时冻结 |
| Pruned duplicated Left | 10,713.948 | 1,207 | 仅Left |
| Pruned duplicated Right | 10,722.460 | 1,207 | 仅Right |
| Pruned configurable Left | 10,652.236 | 1,197 | 仅Left |
| Pruned configurable Right | 10,654.896 | 1,197 | 仅Right |

相对已裁剪 duplicated，configurable 的 source 面积约多3.74%–3.83%；相对两种固定特化中的较小实现，约多4.40%–4.43%。固定 duplicated 残留的10个额外顺序单元是此次综合结果，不能把任何一行称为电路面积下界。

因此可以支持的表述是：**目前可配置实现以约4%的source映射面积代价保留方向选择，并在已注册轨迹中保持固定专用实现的服务。** 原来35.6%的节省仍是相对未裁剪duplicated的事实，但不足以单独支撑架构创新。

现有部署36个memory中18个选方向2、18个选方向3。[后续模板复用核验](reports/TEMPLATE_BINDING_REPORT.md)已找到18个0°、18个180°实例的区域几何构造：146条overlap边和当前bank字节份额保持不变。它尚未验证HB pad位序、DRAM宏及逐实例曝光方向的制造合法性，不能宣称固定裁剪不可行，也不能宣称已经实现。HB pads、备用长线和RX均未在上述面积对照中重新计价。

四种固定特化分别与动态配置输入保留的mapped configurable逐周期配对：共28项、362,616个配对周期，每侧完整交付249,668个字；payload、目的地、ready/valid与停顿计数一致。左右方向均覆盖纯Home、纯Shared、混合、突发、背压、长停顿、尾部。独立读回重建六份统计和28份日志，与旧mapped回放一致。这是零延迟功能验证，不是STA关闭或新的P&R。

[本轮manifest](../artifacts/results/endpoint/static_binding/manifest.json) · [独立核对](../artifacts/provenance/static_binding/audit.json) · [原始综合和回放证据](../artifacts/provenance/static_binding/static_binding_evidence.tar.gz)。源码 `85a27c0`，hn072服务器执行。第一次启动在映射检查将Yosys的scope元数据误认成未映射cell处退出；修正统计后从新目录完整运行，失败运行不计入上述结果。

## 真实需求证据也需要强映射基线

原同owner实验适合隔离fabric能力，但不能自动代表系统最佳设计。例如C/RX3：

| 窗口 | 原trained Home | C/RX3 | Modulo Home |
|---|---:|---:|---:|
| h0 batch1 | 36,878 | 28,977 | 18,439 |
| h0 batch4 | 55,317 | 47,417 | 36,878 |
| h1 batch4 | 36,878 | 28,977 | 55,317 |
| h2 batch16 | 73,756 | 57,955 | 73,756 |

单位为slot。前两个窗口C相对同owner Home有收益，但比简单modulo Home更慢；后两项则保留共享机会。Modulo对照来自N128，C为N192，基线未获得更多请求容量；已有成对Home N192处时间相同。这里是已完成实验的诊断，不将不同预算直接宣称为新的公平性能竞赛。

账本同时报告两种Home，不逐窗口挑更有利的基线。每窗口取二者最小值仅作为显式标注的事后乐观诊断；它不是可部署的布局，更不是新的测试成绩。

C/RX3在五个有正wide收益的窗口保留约81.82%–83.32%的增量，同时增加接收状态。它相对wide少16.67% lane、少18.63% wire proxy，TX+RX payload proxy却多71.43%。这些坐标各有取舍，不能总结成总体成本只剩55%–70%。现有RTL beat reservoir与系统整字RX reservation还不同，不能把C的模型收益直接配上B的P&R面积。

## 本轮已检验的研究问题

> 在同等离线优化机会、冻结部署和完整成本口径下，有限共享是否仍比优化后的private memory有值得制造的收益？

已保持H/plus、slot原生服务与请求预算不变，完成Home/k2/wide/C各自冻结cohort owner与边际LPT的81次回放。它没有额外运行新的modulo Home，也没有优化伙伴或释放placement；不能称全局最佳静态组织。旧同owner单因素对照继续保留，布局收益与fabric收益分别报告。

成本侧将未裁剪、固定专用、可配置三个实现并排保留。最终要报告的是：任务完成收益、模板适应范围，以及为这种适应范围多付出的完整路径资源。先用现有RTL明确哪个服务合同可以兑现，不扩展新的FIFO搜索或跨bank engine pool。

若优化后的Home消除了大部分收益，或固定专用/合法重用方式同样便宜好用，就应缩小或修正贡献；若共享在独立需求上仍有稳定的同成本优势，再扩展制造模板和物理验证。DRAM后端作为可选敏感性工具保留，暂不继续批量扩跑。

## 2026-10-08新增结果与设计方向

[81次冻结cohort回放](reports/COHORT_REPLAY_REPORT.md)已完成：Home/k2九窗映射持平，C改善两个，宽k3改善四个但退化一个。各自冻结cohort布局后，C六窗口快于Home，一个相同，两个慢2槽。全部81项距必要资源下界最多11槽/0.0173%；九组C duplicated/configurable服务相同。原166次/66行汇总仍为历史实验，不悄悄并入新成绩。

同一B接口与HBM2组织的[两次原生驻留诊断](reports/NATIVE_MATCHED_RESIDENCY_REPORT.md)已完成：8/13改1/2使完整对象读时间减少17.44%，没有增加原生或接口能力。这支持按真实原生服务域选择比例，尚非完整batch结果。另有[48项局部beat见证](reports/BEAT_RETURN_CONTRACT_REPORT.md)，显式计费HB流水和RX，没有改RTL或替换系统合同。

接下来优先联合配置原生服务域、静态驻留和请求/返回容量，保留真正独立的DRAM并行度；具体顺序与必要界见[第一性推导](methods/WAFER_DRAM_SERVICE_PRINCIPLES.md)。跨bank聚合是否值得，由原生共享总线和新增汇聚成本决定。hn072独立81次复跑现已完成，服务器与本地审计均通过；与eex005的全部执行字段精确一致，只有运行耗时和线长代理浮点尾数不同。[复现身份与核对](../artifacts/provenance/cohort_replay_replica/completion.json)单列，不作为更多workload样本。

原文与代码核对补记：上游要求identical reticles，但未明确禁止混合朝向；公开构造器采用整层统一模板，没有逐实例orientation参数。我们将同朝向、条件混合朝向和静态变体分开比较，不能借原文排除旋转裁剪强基线。[具体原文定位与推论边界](reports/TEMPLATE_BINDING_REPORT.md#对照-nw-design-for-wsi-原文与代码)。
