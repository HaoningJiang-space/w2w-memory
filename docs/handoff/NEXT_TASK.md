# 下一项开发任务：统一服务合同下的 exposure 候选比较

**状态：待开发。这里的类型与接口是建议，不是已有功能。**

## 目标与边界

回答：在相同资源上限下，home-only、balanced k2 reciprocal、full-bank k3 pair 中，哪种 exposure 与接口实现组合最值得？是否能在保留服务的同时少用连接、lane 或缓冲？

保持现有 H/plus/36C+36M；暂不搜索新 placement，不新增 FIFO 仲裁算法。各架构的数据布局可以有其合法静态构造，但必须在全部场景前冻结并记录哈希。把“换 exposure”和“换驻留”的贡献分开报告。

## 推荐实现顺序

### A. 定义显式候选与成本账本

放入 `w2w/synthesis/` 的数据结构至少包含：geometry_id、repeated_mask、endpoint_implementation_id、address_policy、物理 route 支持、port_widths、frozen_layout_hash、cost_vector、适用流量条件。

成本向量至少分开：bank-port connections、wire/bit-mm、export lanes、configured HB、endpoint storage、pipeline storage。先给各项预算和 Pareto，不用未经校准的加权“面积”冒充 PPA。

区分“已制造但本场景不用”与“确实不配置”的硬件。mask 指向零宽 port、重复收费或隐含免费输出必须检出。所有 reticle 实例由同一模板提供支持。

### B. 为每个候选定义合法驻留

- Home-only：`StripedLayout.home`，在同样对象内交错能力下评估。
- k2：`balanced_assignment` + `StripedLayout.reciprocal`；显式保留边缘未配对 bank。
- k3：`paired_layout`；沿用已验证18对并冻结。

这些是强候选，不预先要求新方案必胜。对照时标明是否改变驻留；不能将 k3 的整个对象配对公式套到 k2 的分组共享。

### C. 接入可兑现服务

优先复用 `FixedService` 字节等式与 `EndpointFixedService` 的资源账本。每种实现需要声明地址可达、物理可达、parent/endpoint/shared-path 约束。

可以先为明确可分解的小结构构造执行见证，再用全局 LP 核验。超出 `execute()` 两目的范围或唯一 route 前提的候选，应标为 unsupported，或者补独立验证后支持；不能默认获得 ideal pooling。

接口应分别返回：流体 upper envelope、可执行 schedule 的 achieved service、适用条件。场景特定 `with_delivered_caps` 不是可任意重用的资源合同。

### D. 先评估再综合

先做三个基线的全负载、单活动、同组活动、独立组活动与 random9。对可解析 pair 用精确期望；k2/混合结构使用正确的活动事件，必要时求服务 LP。不能人为补齐边界。

随后完全枚举有限目录、应用同一预算和服务目标。明确 minimum=0 与 minimum=1 两种 Pareto 目标。先不引入巨大 MILP；当配置共享资源、可组合且可分解条件明确后，再构造配置 ILP。

## 必须通过的验收

- 字节：每个对象/条带仅驻留一次；每个数据源服务等式成立；总容量守恒。
- 路径：R与Y同时合法；移除必经路线会降低服务或导致不可行，不能自动寻找不存在的路。
- 资源：bank parent不重复；port/HB/controller聚合不超预算；未选出口不能出流。
- 合同：固定份额、串行、buffered 的差异真正进入服务求解；不能只改名称或成本。
- 见证：小构造的完整字执行与服务 LP 相容，明确哪些结果只有上界。
- 回归：原63项测试继续通过；新测试覆盖k2边缘、非对称活动、不同用户共享父资源以及成本重复计数。
- 统计：合成分布与真实trace分开；如离线优化布局，只用训练/验证选择，测试冻结。
- 报告：吞吐、common、保底、不可行/unsupported、成本向量、来源提交和哈希完整。

## 交付物

1. 可复用候选适配器和统一账本，保持模型不依赖实验入口。
2. `w2w/experiments/` 下一个注册入口，新增命令进入 `commands.py`。
3. 同预算对照与 Pareto 原始结果，保存 `artifacts/results/`。
4. 独立核验脚本、必要测试、方法和报告。
5. 用一句清楚结论说明：改善来自何处，是否超过强基线，或为什么没有。

## 停止扩展的条件

发现接口支持、物理路径或成本账本无法对齐时，先解决这个具体问题，不扩大mask搜索。若全部改进只来自超过预算、把复杂接口视为免费或改变数据语义，该结果不计为改进。若强基线仍最好，保留它并报告约束/上界证据，再决定是否值得打开placement自由度。
