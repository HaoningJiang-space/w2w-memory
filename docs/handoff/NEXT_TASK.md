# 下一研究任务：低成本 Configurable Shared Egress

用户最新收敛：设计适合 repeated-reticle WoW Memory-on-Logic 的低成本共享接口。
Matching、静态布局、endpoint execution 和 cost model 是支撑；暂停它们各自的新算法支线。
此前目标服务逆向综合的任务优先级已被本项替换。

## 已完成的具体结构

[单因素报告](../reports/CONFIGURABLE_SHARED_EGRESS_REPORT.md)，实验源码 `7604acb`：
Home FIFO + 一个可配置方向的 Shared FIFO；每 memory 在完整布局冻结时确定共享方向。
相同 A/B 位宽、数据、配对和 workload 下，服务保持，endpoint 存储分别减少 33.3%/40%。
原有 serializer、driver、两条长线和 HB 仍保留。计入 pipeline 后，两项存储合计减少
4.54%/7.45%；新方向选择器尚未做 RTL/PPA。

22 项测试与 441 个 LP 通过，原始证据在
`artifacts/results/endpoint/static_shared_fifo.json.gz`。

## 最近研究问题

围绕一条真实接口路径确定：原生完整字、分派、FIFO、静态方向选择、serializer、driver、
接入线、HB 分别位于哪里；哪些资源可共用，哪些因空间位置必须保留。
本轮选择器在 bank 侧、serializer 之前，只验证缓冲复用。下一步应对选择器/局部接线
和发送逻辑给出一致的实现计数；若再合并 serializer，作为单独变化明确比较。

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
实验继续在 eex005 隔离目录运行，保留固定数据、物理可达、完整字服务与源提交记录。
