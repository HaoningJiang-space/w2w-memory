# 冻结cohort映射的独立请求回放

2026-10-08。参数在读取本轮测试routing和执行前冻结。

使用已归档`9f647c8`训练探针的Home/k2/wide/C四份owner，不重新搜索。
各自与探针使用的边际LPT起点比较；伙伴、位宽、驻留比例、每compute常驻对象数不变。
全部128个layer0专家常驻，每对象18,878,976 bytes，逐32-byte字完整读取。

从原256-request语料排除旧48个计时请求、64个训练请求及上一轮48个测试请求。
仅按ID哈希(seed8110)在每subject剩余请求中选择6条，分成三个各16请求的组；
组内按独立ID哈希排序。三组分别取layer0的decode step17/65/113，
各取嵌套batch1/4/16，共九个冷读窗口。总计48个新请求，组间不复用。
该语料已有总体characterization，不称完全未观察的新数据集。

主对照：4种结构×2种owner×9窗口=72次。
实现消融：C duplicated使用与C cohort完全相同的trace/布局/位宽/请求容量，再回放9次。
共81次。比较完整任务时间、每task等待、原生/路径负载和相同硬件下的映射收益。
不以平均带宽倒数代替任务时间，不按测试窗口重新选owner。

固定N192、RX3、request/native/link=1/0/1 slot、每compute每slot最多64个请求字，
always-ready RX与原生slot供给。每次最多80,000,000字、500,000槽，超过限制报错，不采样。
本轮使用原整字预留合同以隔离mapping收益；不混入HBM2组织或未验证的beat-buffer替代。
duplicated/configurable比较完整任务、逐路径、stalls和delivery hash。

准备阶段逐文件验证原始routing，归档提取的layer0 routing和所有逻辑trace。
独立审计重建ID划分、选择的token、全对象/全任务、布局字节与资源下界，
并拒绝缺失case、改变owner、减少字节、改变原生账本和重复记录。
冻结输入/执行/审计分别记录源码、协议SHA、输入SHA；旧结果不重跑、不改写。
原始routing留hn072，执行在eex005隔离worktree。
