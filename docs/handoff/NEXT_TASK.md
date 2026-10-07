# 下一研究任务：先判断 Configurable Shared Egress 的架构收益

**最新：用户已明确source侧HB前选择、三个直接RX，推进最小TX→RX功能对照。**
当前按[ENDPOINT_ROUNDTRIP](../methods/ENDPOINT_ROUNDTRIP.md)实现与验证1M→3C；
只比较独立出口与可配置出口，相同word trace/位宽/背压/RX，首验收为bit-perfect。
HB前source保持memory侧数字功能边界；不使用logic侧隐含转发。
新增握手寄存器、RX重组都单独计费。当前不扩wafer实验或运行PPA。
下面“暂停RTL”的段落是此前顺序记录，本次仅恢复上述范围的功能验证。

用户最新收敛：设计适合 repeated-reticle WoW Memory-on-Logic 的低成本共享接口。
Matching、静态布局、endpoint execution 和 cost model 是支撑；暂停它们各自的新算法支线。
此前目标服务逆向综合的任务优先级已被本项替换。

**最新顺序：architecture model → 确认结构值得做 → minimal endpoint RTL → synthesis/PPA。**
当前停在架构比较阶段，不继续RTL、综合或DRAM bank/controller实现。
已经提前做的小型endpoint原型作为探索证据归档，当前仍按架构比较的顺序推进。
最新[架构决策与三组织比较](../reports/SHARED_EGRESS_ARCHITECTURE_DECISION.md)覆盖下面的历史状态。

## 已完成的具体结构

[单因素报告](../reports/CONFIGURABLE_SHARED_EGRESS_REPORT.md)，实验源码 `7604acb`：
Home FIFO + 一个可配置方向的 Shared FIFO；每 memory 在完整布局冻结时确定共享方向。
相同 A/B 位宽、数据、配对和 workload 下，服务保持，endpoint 存储分别减少 33.3%/40%。
原有 serializer、driver、两条长线和 HB 仍保留。计入 pipeline 后，两项存储合计减少
4.54%/7.45%；新方向选择器和局部接线尚无库映射PPA。

22 项测试与 441 个 LP 通过，原始证据在
`artifacts/results/endpoint/static_shared_fifo.json.gz`。

## 最近研究问题

使用已完成的独立出口、共用FIFO、共用FIFO＋发送器三组织比较，判断现有服务收益是否值得
新增硬件。补充源码 `3c60583` 的23测试、126 LP通过，共用发送器仍保持服务。
它不再减少lane、endpoint或pipeline存储；局部接线长度未知，不能虚报bit-mm下降。
B的FIFO-only局部可见总线由旧示意的256 bit修正为384 bit，详见最新报告。

近期输出是强基线下有意义的预算区间、服务目标和局部成本收支条件。
保留宽Home＋窄Shared＋冻结数据比例的架构骨架，共用发送器作为可选项；
不要凭serializer实例数减少就认定总成本下降。现有证据不足以声称整体硬件大幅节省。

最新合同核对见最新报告§5：窄出口依赖跨字gearbox；当前探索接口是slot-credit，未验证
标准ready/valid的停顿稳定，也未实现RX重组。先将RX、metadata和credit延迟的成本边界
纳入架构判断，不扩大RTL。正式RTL以后只接外部native word/role，周期比例留在testbench。
Logic-side endpoint不能直接套用原memory侧路线；HB之后能否到另一个compute必须显式证明。

固定 H/plus、配对和数据作为第一组因果对照。保留 private、k2 direct、独立 k3 A/B、
full-width direct；对相同服务比较资源，不能只与昂贵的 buffered 基线比较。
目标是用少量额外硬件回收有用闲置服务，是否值得由完整成本决定。

## 已有诊断，不必重复扫参数

k2 direct 的同一 36C random9 总体中，20 个无 private 瓶颈客户端均值 1.589916，
另外16个为1，全体1.327731。继续加宽已足宽出口不能修复覆盖或多伙伴依赖。
这项诊断用于定位投入，不立即展开边界修复/placement 搜索。

## 暂停与后续

暂停新的 matching/cycle、更多 arbitrary k、深 FIFO scheduler、BO/Benders/DSE。
旧代码和证据保留为复现与对照，不因“暂停”大规模整理工程。
Placement co-design、原生时序校准和真实 trace 在接口机制与成本依据稳定后再接入。
小RTL仅在架构比较支持继续以后再恢复，范围限定新增endpoint块；当前不扩展已有探索原型。
实验继续在 eex005 隔离目录运行，保留固定数据、物理可达、完整字服务与源提交记录。
