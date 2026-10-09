# 静态共享方向复用：单因素架构实验

基线 `541ab80`，输入 `artifacts/results/endpoint/architecture_competition.json.gz`。
本轮只把 k3 A/B 的两个互斥 shared FIFO 合并为一个 bank-local shared FIFO。
固定 H/plus、36C+36M、32 banks/M、原生时序、配对、数据比例、位宽、物理线路和 HB。
保留每方向 serializer、驱动与 pipeline；新增 W-bit 静态 1:2 方向选择器。

## 显式实现与适用条件

`EndpointSpec.shared_fifo_ports` 说明哪些物理出口共用一个 FIFO；
`MemoryFabricDesign.shared_directions` 为每个 memory 冻结一个物理方向。
方向根据完整布局编译，不能根据某个 activity set 重新选择。没有 peer 字节的实例仍
制造完整模板，配置任一固定合法方向但不发 shared 请求。

只有等宽、等深、bank 端缓冲的方向组支持本轮复用。完整字执行实际只分配一个共享队列，
并检查逐槽守恒、容量及周期边界。布局使用其他方向或同时依赖两个 shared 方向时拒绝。
Service envelope 将未选择的 bank-output 容量置零；物理线路与 HB 配置成本保留。

数据路径在 memory 层为：原生完整字 → home/shared 分派 → 两个 FIFO；shared FIFO 的
256-bit 读出经静态方向选择器送至两个保留的 serializer 之一，随后为各自的窄长线与 HB。
HB 之后直接到达其物理 compute 接收者，无转发或跨 compute 换方向。

本轮不合并 serializer。这样只检验存储复用，方向选择器按 32 个 1:2、每个输入 256 bit/
输出合计 512 bit、每 M 一个广播方向配置位计数。本地选择器连线长度与 gate 面积未知，
单列为未校准项，不把 endpoint 节省百分比当成净面积节省。

## 冻结对照

从上一轮归档重建 random9 优化的方向 2/3、18 对 A/B，分别与其复用版本比较。
并保留同配对 k3 direct、k2 direct 和 home direct 强对照。A/B 的布局哈希、路径、位宽
及其他硬件计数必须保持相同。A 为 256/128/128、D111、比例 2/3；B 为 256/160/160、
D122、比例 8/13。不新增深度或 placement 扫描。

评估：每设计 full、single、one_pair、一个注册 random9、first9、全部16个 clustered 窗口；
每场景走公共执行器及吞吐/common/上界 LP。random9 用完整 36C 的精确邻域期望。
从 k2 的实际 bank 所有权划分 private 瓶颈组与其余组，同一组索引用于所有设计，不删除边缘请求。

旧 A/B 实际使用的 10 条不同序列（home-only 各一条，加两个方向各自 single/shared+home）
与新实现在每个固定方向逐一比较。home-only 在两个配置下各验一次，因此共 12 次配置比较。
额外测试带 downstream credit 停顿时的等价，并保留同时使用两方向的反例：独立 160-bit
两口为 1，强行压成一个 160-bit 口为 .625；正式静态实现应直接拒绝这种输入。

## 输出与结束条件

报告同服务下的 endpoint、pipeline、wire、lane、HB、serializer 和选择器计数；
endpoint+pipeline 合计变化单列，方向选择器未定价时不宣称完整成本严格支配。
重新确认 k2 的 20/16 客户端分解，不扩展边界修复或优化框架。
代码、测试和原始结果归档；所有模型执行在 eex005 隔离目录进行。
