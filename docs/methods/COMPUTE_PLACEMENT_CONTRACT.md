# 固定 RWDL：数据汇聚与靠近分片计算

这是一项新的资源与传输合同，历史 `35f7e17` 和 `2e3087a` 结果保持冻结。
固定四 token、同一 128 expert owner、36 个共享 compute engine、36 颗 512 MiB
memory、每 tile 2 MiB SRAM、相同坐标/NoC/credit/MC32/requester32；没有新增算力。

## 明确的传输服务

1. 本地 DMA 只搬 payload，按接收写口的 256 B 拍拆分。整包和 streaming 使用
   完全相同的排空路径，4 KiB 均消耗 16 个 SRAM 写拍；只改变字节可用时刻。
   本地 NI 预约按 payload 占用的数据 flit 数计费，header-only 控制仍占一个条目。
2. 远端保持原有单-flit packet 的固定 cell 网络。每 message 保留 16 B envelope，
   每 cell 另有 **64-bit sideband**：source6、destination6、class2、tag16、ordinal8、
   valid-payload-length10、first/last2、reserved14。所有 hop 都支付 sideband 线长、
   pipeline register 和输入 buffer 存储。simulation ID 与路径历史不是线上的信息。
   16-bit tag 在 packet 准入到完整交付之间从有限池分配，交付后复用。
3. 接收预约与 tag 分配明确为**理想的全局预约参考**；尚未模拟远端 grant/ACK 的
   控制流量或 RTT。它保证存储有限，但不是已物理实现的协议，不据此声称 WoW 闭合。
4. Native source FIFO 不改变仲裁。只统计队头缺数据、后方有数据、其中注入 credit
   可用的周期，并保留阻塞 message 身份。trace 模式在当前 partial queue 排空后才生成
   后续 message，因此统计包含已准入/已供数但还没有生成 flit 的 source 队列；
   不能只扫描 partial queue。这些指标互相重叠，不相加为总 stall。
5. 两项架构都显式提供一个独立 256 B/ns activation/partial-state SRAM 读口与
   一个 256 B/ns 接收写口。源端先预约有限 NI，再逐拍读取并释放 SRAM，不能瞬间
   免费复制一整个 activation。计算内部权重读服务仍包含在既有计算吞吐假设中。

## 原生阶段与几何边界

RWDL source 位于 array digital port。RD 后的实际 array-ready 时刻保留为
native callback tail 减一个 3760 ps beat；callback 是同一 RWDL/HB 数据拍结束，
随后明确经过有限 CDC 与共享 aggregation，才在 home MC 交给 NoC streaming。
array-side ready、beat tail 和 controller-ready 分别记录；没有第二条重复 HB 总线。
其 array/refresh 时序假设见 [RWDL 原生合同](RWDL_NATIVE_SERVICE.md)。

聚合 tile 是一个共享的 4096 MAC/cycle 时序 engine、2 MiB SRAM、一个中心 router/MC
和上述读写口。它不等于一个实际 core 或已完成的 reticle floorplan；SRAM bank 数、
实际 core 数、logic/array 面积和片内 wire 距离未知。当前资源密度未标定，面积 DSE
不可用。修改 field 尺寸默认拒绝；显式允许时仅作为固定资源的距离敏感性，不能
把缩小尺寸同时保留资源的结果宣传成可部署设计。固定本轮的 26×33 mm。

## 三项冻结执行

| 配置 | 权重/计算放置 | 就绪策略 |
|---|---|---|
| gather-stream | 原 4-way 分散权重、固定 owner 执行全部 12 blocks | 流式 |
| gather-whole | 同一图、同一 native profile 与所有服务合同 | 完整 descriptor |
| near-shard-stream | 四节点组各存并执行三个完整 intermediate blocks，owner reduce | 流式 |

第三项是普通 intermediate tensor partition 强基线，不是新的算法贡献。FP8 权重及
FP32 scales 不复制，总权重/MAC 工作保持相同，所有 128 expert 布局预先冻结。
每个实际 engine 串行共享所有被放置到它的 partition；每 partition 内仍为 blocking
128-wide tile，传递 BF16 输入和 FP32 部分和。四份 partial sum 返回原 owner，显式
计入 3×n×4096 个 FP32 reduction add，以及有限 SRAM、源读口、写口与网络。
数值不在本 simulator 验证范围；浮点归约顺序变化不称为 bit-exact 推理。

输出原生服务、关键链路、源 FIFO、SRAM 读写和 compute engine 的压力表。native
admission、RX job wait 等含有重叠等待；只报告各自原始计数、服务工作和任务时间线。
没有证据前不加 Direct HB，不换 router，不做大规模验收或 reticle/endpoint DSE。
