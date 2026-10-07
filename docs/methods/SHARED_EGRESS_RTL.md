# Configurable Shared Egress：数据通路实现对照

基线 `a8971f7`；沿用 `7604acb` 的冻结 A/B、18 对、H/plus、原生 profile 和 workload。
这一轮实现寄存器 FIFO 与 payload packetizer，比较以下三种组织：

| 模式 | Shared 存储 | Shared packetizer | 方向选择位置 |
|---|---|---|---|
| 0：独立 | 每方向一份 | 每方向一份 | 各自入口 |
| 1：只共享 FIFO | 一份 | 每方向一份 | 宽字视图到 packetizer 之前 |
| 2：共享 FIFO+sender | 一份 | 一份 | 窄 beat 到物理线路之前 |

A 为 128-bit、D1；B 为160-bit、D2，Home 均为256-bit、D1。
每个 memory 的方向配置输入在两次 reset 之间固定，综合时保留为输入而非常量。
两个物理输出都存在，禁止通过对每个实例常量折叠删除重复模板。

## 周期与数据含义

256-bit native word 分成8个32-bit单位。每槽先看旧队列是否可收完整字，再排空输出；
不能利用本槽稍后释放的空间再次接收。队列深度包含正在发送的字。
Sender 可将当前字尾和下一字头拼成一个 beat，返回有效32-bit单位数；下游提供全宽
ready/stop credit。测试包括原生停顿和各方向独立反压。
不声称这个实现已支持任意逐bit credit、write traffic、跨时钟或真实DRAM timing。

宽度粒度固定时相位步长为 gcd(W,w)。D2最大跨字读视图为
`W + w - gcd(W,w)`，所以B实际需要256+128=384个有效输入位。
源码接口可用两个256-bit向量表示，但未使用的高128位应由综合移除。
这也修正了前轮“只共享FIFO”的W-bit局部选择器简化计数。

Memory层数字外围放置FIFO、packetizer和方向选择；选择在第一次HB之前。
本轮不移动bank/port，不减少驱动位数、长接入线、pipeline或HB信号。
局部物理布局尚未完成，报告有效总线宽度及由长度决定的bit-mm系数，不指定虚构线长。

## 验证和计数

- 固定6个硬件配置：A/B × 3种组织。无宽度、深度、placement或matching扫描。
- 独立oracle使用32-bit token FIFO验证每槽准入、每个输出的有效数及payload；最后排空并
  比对各端口输入/输出哈希。与仅比较字数的周期执行器形成独立检查。
- 每配置测试两个方向的home-only、shared-only、比例混合、native burst、随机反压、错误
  方向输入，共12条有限轨迹。前三类测量窗口与原完整字周期执行比较速率。
- Icarus分别仿真RTL和Yosys输出的通用门级网表；综合使用相同flatten/noabc再ABC simple流程，
  保留可配置输入。统计各类FF、MUX及逻辑门，检查无latch。保存源码、工具版本和网表哈希。
- 新shared-sender A/B回放原21场景，共126个LP；旧FIFO版本的逐C服务和common均应保留。
- 23项相关Python测试检查成本口径与小系统服务；保留既有private/k2/direct结果作对照。

这属于可综合RTL与通用逻辑计数。没有标准单元库、placement/routing、STA或功耗校准，
不将generic cell数转换成mm²，也不由逻辑仿真宣称1.024ns时序已闭合。
每memory的32个bank逻辑可分别计数，但物理驱动和接入线仍单列。
