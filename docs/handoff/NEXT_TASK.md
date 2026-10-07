# 下一研究任务：固定几何、面向目标服务的接口与数据综合

2026-10-07 更新。工程整理和公平架构竞争已完成；见
[架构竞争报告](../reports/ARCHITECTURE_COMPETITION_REPORT.md)及
[冻结设计族](../methods/ARCHITECTURE_COMPETITION.md)。当前用户顺序优先于前轮 native-profile 支线。

## 已经得到的研究判断

- Home/k2/k3 均位于性能–lane–endpoint storage–wire 前沿；不能删除 k2 或只扩 sharing。
- Random9 下 k2 direct 为 1.327731，使用 16,384 lane、8,192 endpoint bits、241,561.6 bit-mm。
- K3 A 为 1.385714，lane 相同，但 endpoint 存储 3 倍、wire 多 23.16%。
- K3 B 为 1.482143，代价为 18,432 lane、40,960 endpoint bits、341,664 bit-mm。
- 接口和数据比例决定独占 γ；伙伴依赖、边界和 workload 决定活动系数 G。
- Cluster 优化选择与 random 不同；布局在设计阶段冻结，不按活动样本重选。

## 最近一步

保持 H/plus 和当前数字原生模型，用本轮精确目录作参照，构建目标服务驱动的筛选：

1. 给定目标平均服务 t，按结构的 G 反推 γ_required=1+(t−1)/G。
2. 用原生、完整字位宽、重复模板及成本下界淘汰不可能实现。
3. 从剩余接口生成宽度/深度和固定条带比例，执行验证满载与独占服务。
4. 输出达到目标的成本前沿，以及离当前结构上界的差距。
5. 与本轮有限精确目录比较结果质量和实际执行次数，再有针对性地放宽 k2 bank 分组或非均匀接口。

本轮已自动选择角色接口、比例、方向和配对，下一步应提高逆向综合能力，避免把重新扫描
同一目录包装成新算法。目标 1.3 的低成本 k2 和目标 1.4 的 k3 成本前沿可作为具体任务。

## 保持的实验口径

同一逻辑数据、原生服务、满载保底和合成活动分布；每种结构独立设计并冻结物理驻留。
执行器、LP 与成本读取同一 Design。所有接入线、未用模板方向、endpoint 和 pipeline
分别计账。保留 direct 强基线、上界与可重复执行见证。最优性只对明确的设计族声明。

本轮精确结果位于 `artifacts/results/endpoint/architecture_competition.json.gz`，
全部前沿设计通过公共执行器/资源组合检查；作为后续验证参照即可，不必先重做全部历史实验。
实验在 eex005 隔离目录运行，Git 保持 main 并及时推送研究里程碑。

## 后续顺序

先稳定接口/exposure/静态布局综合，再让 placement 改变方向、路径长度和宽度成本，
最后接真实 MoE/LLM trace 检验时空不均衡。Native-ready 敏感性已有前轮证据，作为之后
校准维度保留。本轮结束后不继续工程重构、不新增 FIFO 扫描、不提前释放新 placement。
