# 按出口角色综合接口与静态驻留：注册协议

本轮基于 `2e8e8ed`，固定 H/plus、36C+36M、32 banks、256-bit/native slot
（1.024 ns）、原生总服务、逻辑数据量和 controller 上限。不改变 geometry。
研究 home/k2/k3 在各自合法、场景前冻结的驻留下的服务—成本前沿。

## 执行与组合 Gate

新增入口保留旧 execute 回归。ImplementationSpec 同时决定输出宽度、存储和
成本；每槽先发起至多一个完整字，再按输出发送。buffered 的 D 包含 serializer
中的字；direct 使用每 bank 一个共享 holding register。按整数静态份额编译固定
顺序，不越过满队列的字。活动源消失可以过滤其字，活动源不得重标地址或出口。

用有限状态周期检测获得精确可重复服务，状态包括请求相位、原生就绪相位、credit
相位及各队列剩余 bit。每槽检查位/字守恒。未找到重复状态不能宣称长期可达。
native_ready 是接收机会序列；不是已经产生且必须缓存的 DRAM 返回 trace。

每个 C–bank 必须有唯一路径；逐路径回标完成率。检查所有活跃/可用端点的最坏
瞬时输出之和不超 memory port、HB、compute port/controller。这是保守组合证书，
而非平均 LP 代替队列验证。若不满足则拒绝组合，不把独立端点结果相加。周期执行
提供服务槽预约；未使用的预约可置空，保留原槽时序，不能压缩后重新竞争资源。
不模拟长线传播延时；pipeline register 数只是阶段化成本代理。

## 冻结目录与比较

- home：完整本地布局，256-bit direct。
- k2：minimum-wire balanced (0,2)/(0,3) bank 分组，边缘 bank 保留本地；
  home=256，共享宽度 64/128/160/192/256；各自比较能力匹配比例和 half/half。
- k3：原18对，192/192/192 D2 等宽基线、256-bit direct 强基线，以及
  home=256、shared=64/96/128/160/192/224/256 的能力匹配比例。
- 消融：A/B 的接口配原 50/50 数据；固定原比例没有相同的改进保证。

给定 home H=1、shared S=w/256，匹配 home 比例为 256/(256+w)。每个结构的
完整逻辑对象保持相同，物理比例各自冻结。k2 不使用配对总体公式，按每 compute
实际依赖的所有邻居活动模式精确枚举，再以超几何概率求均匀9-of-36条件期望。
只有满足逐槽组合证书的结构才采用这一局部模式分解。

各候选验证 single、one_pair、独立配对、注册 random9(seed620100)、first9、full。
同时求流体上界、执行回放的吞吐与 common completion，记录满载服务与残差。
比较 lanes≤18432/storage≤49152 的目录最优；另列无此预算限制的256 direct参考。
记录多成本 Pareto，不用加权面积分数。

## 成本边界

每 memory 计全部重复模板连接，包含实例闲置方向。分别登记 bank 端序列化与
port 端序列化时的长线 bit-mm、pipeline bits；宽度来自同一 ImplementationSpec。
未知 bank 本地 selector 接线长度不填零当测量值。端点存储替代旧 buffer proxy，
不叠加。HB signal bits、控制序列 ROM/counter、selector输入另列；没有校准面积、
功耗、拥塞或时序 signoff。控制 ROM/counter 是明确编码代理，不代表最小控制器。

## 敏感性与停止条件

只对等宽基线、A、B、wide direct重复 always-ready、alternate(10)、burst(11110000)
的周期供给；额外做192-bit D1/D2单口诊断。供给减半时同时报告绝对速率和原生上限，
不把 full<1 当接口独有退化。原生供给模型未经真实DRAM校准。

有限对象：登记每 bank 原生字数1/2/3/8/13/32/128/1024；按冻结比例的固定周期前缀
形成整数份额，报告尾部与流体理想比的误差及对应服务容量上界，不冒充对象完成时间。
容量上界与完整字执行见证分别标注。

Gate失败先修复具体语义或成本问题，再运行全目录。保留阴性结果；本轮不扩几何。
