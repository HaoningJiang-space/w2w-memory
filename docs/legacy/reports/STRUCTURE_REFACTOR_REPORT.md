# 结构整理：职责归位与行为一致性

2026-10-09。结构改动独立于 RWDL/返回合同/计算放置的模型提交；运行中的
`placement-source@1b086e0` 始终冻结。没有迁移 native 构建树、历史结果或 service/ 整树，
没有因目录变化重跑九项完整层架构实验。

| 提交 | 内容 |
|---|---|
| A `bea9812` | 纯 I/O、两种历史指纹、轻量 revision、纯 system summary、逻辑工作身份归位；切断当前 runner→runner 公共函数导入 |
| B `17220dd` | machine presets/geometry、显式 routing 输入与纯编译；Current/Reference/Legacy 惰性命令导航；重写当前代码地图 |
| C `9f8d6a5` | 本地 DMA serial schedule 与共享 ReceiveWritePort 提取；统一 kernel、NI/事务/credit 生命周期保留 |
| 兼容 `b840b08` | 保留已有接收计数访问，状态仍由写口唯一持有 |

`digest_system_v2` 与 `digest_read_v1` 保留原 JSON 空白、NaN 规则。
旧位置导出兼容别名，旧命令仍可用。`compile_layer()` 保留冻结默认配方；
新 `compile_routed_layer()` 接收已选 routing/owner，无输入选择或文件读取。
机器参数及几何调整不需要修改 MoE 工作负载。两种本地传输合同原样保留：结构
提取没有再次纠正 streaming、改仲裁、改时钟或修改 RWDL。

## 核验

所有测试在 hn072 隔离目录运行，复用冻结 native 二进制。
A/B 相关回归通过，C 的相关回归也通过。第一次 C 检查发现计数访问兼容遗漏，
修复为同一状态的属性视图后通过；失败与修复日志均保留。

[重构前后独立对照](../../artifacts/provenance/rwdl_service/study/structure-refactor-c-audit.json)
比较 `1b086e0` 与 `9f8d6a5`：两个完整 snapshot SHA256 相同，20 个区段无差异。
包括两种历史编码及 NaN 处理、JSON/GZip I/O、两种机器宽度、预定九项输入的
图/metadata（仅编译）、分片图，以及本地/远端小型 whole/stream 原生执行。
后者逐项核对整数 ps 事件、任务开始/结束、native 状态、NI/RX 与写口服务和纯摘要。

[核验脚本](../../tools/audit_structure_refactor.py) 可使用两个冻结 checkout 复查；
这是小型执行与规范化配置的行为一致性证据，不是全仓库形式证明。
构建、运行和墙钟身份允许不同；模型记录、图与事件不能借此改变。

当前地图见 [CODE_STRUCTURE](../CODE_STRUCTURE.md)，当前状态和下一任务只维护
[HANDOFF](../HANDOFF.md)。冻结研究报告保留原路径，由历史索引进入。
