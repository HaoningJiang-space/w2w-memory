# 服务合同是否改变设计选择？首轮受控结果

**答案是会，但这轮证明的是避免模型诱导的错误选择，还没有超过已有强结构化基线。**

源码提交 `8b27f7b`，运行主机 eex005。保持 H/plus、18 对、half-home/half-peer 静态数据、96 条 bank-port 连接、HB/controller 配置不变。只从已验证的 16 个出口实现中选择；不增加物理路线、不修改驻留、不迁移或复制数据。方法见 [注册协议](../methods/CONTRACT_SELECTION_METHOD.md)。

## 相同预算，三种模型选出三个不同实现

每颗 memory 的预算：export lane bits ≤18,432，storage bits ≤49,152；要求满载每个 compute ≥1 TB/s。目标为均匀 9-of-36 活动的期望平均服务。吞吐单位 TB/s/active compute。

| 选择依据 | 选中实现 | 模型预测平均服务 | 实际执行平均服务 | 实际满载服务 | 实际 storage bits |
|---|---|---:|---:|---:|---:|
| 理想独立出口容量 | 192 bit、直接出口 D=0 | 1.385714 | 0.885714 | 0.5，违反保底 | 8,192 |
| 区分 serial/buffered 的流体合同 | 192 bit、D=1 | 1.385714 | 1.000000 | 1.0 | 24,576 |
| 完整字执行候选 | 192 bit、D=2 | 1.385714 | 1.385714 | 1.0 | 49,152 |

三个选择遵守同一预算，实际成本并不相等。流体模型认为 D=1、D=2 性能相同，因此按注册的低存储成本规则选择 D=1；执行模型识别出 D=2 的额外能力，决定花这笔预算。这是容量与实现之间的差距，不是免费的 38.6% 算法加速。

本实现每槽开始派发完整 256-bit 字，然后出口发送。192-bit 出口配 D=1 时，未排空的尾部阻止下一完整字入队；D=2 可以持续派发并利用独立 serializer 的剩余发送额度。结论依赖已声明的离散槽、完整字和仲裁模型，不是所有 DRAM 接口都存在同样差距。

## 不同目标下，设计选择并不相同

同一预算与保底要求下：

- 全负载目标：执行模型选择 128-bit、D=1，服务 1.0。加宽到 192 或增深没有收益。
- 随机 9/36：选择 192-bit、D=2，平均 1.385714，期望公共速率 1.132210。
- 注册混合分布（9/36、18/36、36/36 的权重 .5/.25/.25）：选择 192-bit、D=2，平均 1.257143，期望公共速率 1.066109。

这里直接积分指定的 K-of-36 概率模型，不用训练 seeds。精确的是活动集合平均；底层服务仍是有限完整字执行结果。没有真实应用 trace，也没有据此宣称应用延迟改善。

## 强基线和真实限制

- Home-only 的 1.0 仍是必须对照的低成本服务基线。这轮所有高成本 exposure 在 D=1 窄出口下并未超过它。
- 将 lane 预算放宽到 24,576 后，已有 256-bit 直接配对达到 1.771429（random9），仅需 8,192 storage bits。当前目录没有任何新结构超过它。
- 192-bit D=2 比它少 25% 出口 lane bits，但多 6 倍存储，性能更低。不能在缺少面积系数时宣称哪个更便宜。
- 所有候选继承同样 96 条 exposure 连接及内部 wire proxy，尚未综合更便宜的 exposure，也没有证明 placement 联合优化收益。
- 完整字结果是已执行调度在本对称 pair 场景下的能力；它不是对任意非对称流量通用的 endpoint 容量多面体。

## 构造和复现核对

eex005 全部 **63 项测试通过**。重新运行 64 条 endpoint 轨迹、160 条 wafer LP/执行桥接记录，与目录整理前归档逐字段一致，仅 source commit/host 元数据不同。独立配对公式最大误差 1.11e-16；所有原有 21 份结果字节哈希保留。

新增活动期望公式在 4/6/8 节点上穷举全部非空活动子集核对；候选选择为有限目录完全枚举，不需要 ILP。统计覆盖 16 个预算、2 个保底、4 个目标、3 种选择依据，共 384 条选择记录，其中不可行情况明确保留。

[选择原始结果](../../artifacts/results/endpoint/contract_selection.json)；[本次桥接原始输入（gzip）](../../artifacts/results/endpoint/contract_selection_bridge.json.gz)；[验证凭据](../../artifacts/provenance/contract_selection_verification.json)。解压输入的 SHA256 与选择输出中的 input_sha256 一致。

```sh
python -m w2w run_endpoint_bridge --output memory_results/contract_selection/bridge.json
python -m w2w run_contract_selection memory_results/contract_selection/bridge.json --output memory_results/contract_selection/selection.json
```

## 这轮之后应该做什么

不继续独立扩大 FIFO 扫描。把这份实现能力表作为上层有限配置综合器的输入，再让 home-only、k2、k3 等 exposure 候选在相同资源账本下竞争。优先检查能否减少无用连接/通道，同时保留可兑现服务；随后才让 placement 改变合法候选。只有击败同样经过优化的强基线，才算得到新的架构结果。
