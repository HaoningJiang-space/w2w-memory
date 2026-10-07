# 有限任务与共享成本：2026-10-07 注册

目的：固定 H/plus 和已归档设计，检查有限请求、空间竞争、阶段切换及 join 是否保留共享收益。
这是合成机制研究，不是实际 MoE 或整模型加速。先冻结本文件和源码，再在 eex005 隔离运行。

## 合同比对与时间口径

系统回放沿用 `READ_WORKLOAD_REPLAY.md` 的完整字/bit-budget 模型：每 bank 每原生槽最多
一个 256-bit 字、source 容量包含发送中字、预留整字 RX credit。RTL `endpoint_tx` 另有
输出拍寄存器，`endpoint_rx` 为 Home 256-bit / Shared 384-bit reservoir；两者不逐周期
等价。特别是模型的每路两个完整字 RX 槽不等于 RTL 接收器。旧周期服务见证也不等于有限
DAG 完成时间。保留现有两层结果的边界，不通过把 FIFO depth 加一来伪造合同对齐。

主表仅比较原生槽数；模型 1.024 ns/slot 可留在原始输出，但不当作 ASIC 已验证频率。
RTL 在 Nangate45、2 ns 下的修复后面积只作独立 B / B-configurable 局部证据。
本轮不形成跨模型的 area-delay product、整片面积或系统 PPA frontier，不新增 RTL。

## 冻结设计、对象与任务

沿用现有 runner 的七项：Home direct、k2 direct、k3 direct、A、B、A-configurable、
B-configurable。保留全部有限边界、各自已冻结合法驻留，不按新任务重新选择伙伴或比例。
所有设计使用相同逻辑对象与 compute 所有者：36 个对象，每个 `4*2496` 个 32-byte 字；
未活动对象也占存储。基准读长 2496 words，整除原目录的 32/64/96/416 字条带周期。
请求从对象 word 0 按地址递增；每个长读任务完成后有 8 slots 固定计算，不与读重叠。

按 compute 物理坐标 x 升序定义列、每列内 y 升序定义行的 6×6 索引（保留 H/plus
奇偶列的半行错位），不查询配对或性能来选择活动集合：

| ID | 任务 |
|---|---|
| single | (row=2,col=2) 一个 compute 读取基准长度 |
| dispersed9 | 行、列各取 0/2/4 的九个 compute 同时读取 |
| clustered9 | 行、列各取 0/1/2 的九个 compute 同时读取 |
| full36 | 全部 compute 同时读取 |
| moving9 | 四个 3×3 象限依次读取，每阶段 join 后才进入下一个象限 |
| straggler9 | dispersed9 中 (2,2) 读 4 倍字节，其余读基准量；join 后一个 32-slot 计算任务 |
| short9 | dispersed9 每个只读 64 words，不加读后计算；保留有限尾部与非完整条带 |

各场景最后都有全体必要任务 join，makespan 是实际 DAG 完成时间。
均为确定性诊断例，不声称随机总体期望，也不挑选最优 seed。

## 有限控制实验与停止条件

主配置沿用请求延迟 1、native 延迟 0、link 延迟 1、issue 64 words/C/slot、outstanding
128 words/C、RX 每路 2 words、always-ready。不改变源服务、输出位宽或深度。
仅追加：dispersed9/clustered9/full36 的 outstanding=512 控制；dispersed9 的 RX ready
周期 `(1,1,0,0)` 控制。其余参数全相同；共 11 个 workload/config × 7 designs = 77 回放。
高 credit 不是免费架构升级，新增控制状态未综合，不放入同硬件预算排名。

每次回放保持原每槽守恒/合法性检查。两对 duplicated/configurable 必须有相同任务时间、
驻留、事件哈希、路由计数和 stall。任一失败停止解释结果，先修复；不得跳过失败候选。
每次最多 100,000 slots / 10,000,000 words；不做自适应宽度/深度搜索。

## 分析与产物

- makespan、相对 Home 完成时间、逐任务 read wait 和 join 尾部跨度。
- 以显式依赖和实际 compute 串行顺序反推一条实现的关键路径；memory/compute/release
  时间之和必须等于 makespan。不把所有 task 的 read wait 求和当墙钟时间。
- 对照 credit/RX 控制定位请求供给与背压敏感性；stall 计数的单位不同、可重叠，不能相加
  当 critical-path attribution。记录各阶段同时活跃的共享伙伴数量，解释必需数据竞争。
- lane bits、source buffer bits、wire bit-mm 分项；投影 Pareto 仅覆盖这些已知 proxy，
  selector/control/RX/driver 及实现证据不完整时，不宣称完整硬件成本支配。
- 原始 trace、配置、design/residence/source hashes、机器环境、完整结果及紧凑图表归档。

结果不论正负都报告 full36、short9、clustered9。完成这轮后按实测瓶颈选择下一步，
不扩大 placement、FIFO、RTL 或 matching 研究。
