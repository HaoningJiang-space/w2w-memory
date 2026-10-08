# 下一阶段的服务配置与物理验证

真实 routing 输入闭环已经完成；本阶段接真实 DRAM 命令时序、建立层级物理成本，并判断静态 service provisioning 是否值得扩展。以下为待实现任务，不是新增实验结果。研究判断及数学边界见 [分析](../methods/SERVICE_PROVISIONING_ASSESSMENT.md)。此前 ASIC 交接全文保存在 [历史记录](NEXT_TASK_HISTORY.md)。

## 已合入的新进展与最近实验

最新：[完整返回路径研究](../reports/RETURN_PATH_PROVISIONING_REPORT.md)已完成87＋47＋32次回放，
下述注册实验已执行。RX占位解释并修复了192-bit目标未兑现的问题，所有166记录独立审计通过。
当前系统研究的具体后续是：保留硬件与几何，按训练cohort的共同完成资源下界选择静态owner/伙伴，
与modulo和边际LPT比较；新测试请求另行保留。完整成本、DRAM后端仍按下述独立任务推进。

`11fd2ab` 已加入请求容量感知比例与 189 次合成回放：N128 下 A/B 的 Home=4/5，分散任务均为 73 槽；原来是 79/77 槽。N192 下原 B 更快，比例不能逐窗口免费切换。48 份真实记录只重算下界，没有回放新比例。

先在独立 routing 输入上验证这些冻结候选，保留同等优化的 Home/k2/宽 k3，比较同 N 完成时间与同目标成本。若优化 owner，只用训练部分并冻结，val 用于选配置，test 用于最终报告。候选已存在，不重复开发或先扩跨 bank pool。以下 DRAM 后端与物理成本是此前用户要求，仍需推进。

`55a4fec` 已加入[独立请求协议与准备/运行入口](../methods/PROVISIONING_HOLDOUT_STUDY.md)，
注册 87 个组合；此处不将协议注册称为实验完成。它使用固定解析候选，未调超参数，
因此当前只需训练/测试划分；若以后用验证结果选模型，再单独划分 validation。

## 第一项 扩展已接通的 DRAM 命令参考

已完成 `service/dram` 可替换后端：公开 HBM2、有限接受队列、真实命令推进与完成回调，source 容量先预留，再接受原生请求。8次完整对象回放及193项服务器测试通过；[结果](../reports/DRAM_COMMAND_BRIDGE_REPORT.md)和[复现](../methods/DRAM_COMMAND_BRIDGE.md)已归档。旧 slot 默认语义不变。

下一步在相同 HBM2 资源下扩展完整冻结 batch 和 outstanding/queue 敏感性。当前只抽取了 h0_b1 的第一个完整 expert 任务；不能把这个接口探针当成整个推理结果。HBM2 channel 与原每 memory 1 TB/s 模型预算不同，且公开时序含估算，后续需要可追溯的 WoW 原生数据路径参数，不能用缩放时序去迎合旧结果。

## 第二项 先验证 service provisioning 的可优化空间

现有实现是每 bank 的静态方向复用；不能直接称作多 bank 共享一个发送 engine。先固定几何、地址驻留和 lane/HB 总预算，比较独立出口、删去静态未使用方向的强基线、少量 engine 绑定。明确 engine 属于 bank、bank group 还是整个 reticle。

静态 binding 一次覆盖注册的全部层、对象和需求窗口，测试时不能重绑定。若更少 engine 只能靠未计费跨 bank 互连或逐窗口换方向维持服务，应报告这个缺口。先在流体放松中估计机会，再用有限执行核验；仅对值得继续的设计扩 RTL。布局联合优化在单因素服务实验之后进行，不能将两种收益混在一个数字中。

## 第三项 建立完整路径的层级成本

复用已通过检查的 Nangate45 slice，补 engine binding、跨 bank 连线、仲裁/ID/credit、RX、HB pad 与时钟等资源账本。未实现块用分项区间，不将 bit-mm 换名为面积。分别报告 source、完整数据路径、reticle 和整片估计，区分 measured 与 estimated。

真实工艺 signoff 仍需指定的 logic/DRAM PDK、多角库、DRAM 宏、HB/RDL 寄生和规则、顶层网表、时钟/功耗约束及 DRC/LVS/IR/EM 流程。现有公开单角 slice 结果不能代替这些资产；当前资料路径仍待确认。先完成可复现的公开模型评估。

## 代码放置和交付

- 不可变参数与身份：`domain`；DRAM 后端实现：`service/dram`（已接入）。
- 绑定与布局选择：`synthesis`；endpoint 执行：`endpoints`。
- 参数注册与 CPU 作业：`experiments`；独立证书：`validation`。
- 结果统计：`analysis`；图形：`visualization`；不新增根目录研究脚本。
- 每次新增实现先有最小构造及反例验证，再扩大实验；保留版本、输入与合同身份。
- 本地开发 → 唯一 main 推送 → 服务器拉取实验。原始 trace 与大中间文件留服务器。

本轮文档整理没有安装 DRAM 模拟器、创建上述新包或完成新 RTL/signoff。
