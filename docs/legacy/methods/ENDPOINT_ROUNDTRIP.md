# 最小 source-side endpoint：TX → 直接 HB → RX

2026-10-07，开始运行前固定范围。基于 `cbbf888`；本次按用户最新要求恢复最小功能验证，
不扩wafer性能实验、不做RTL PPA，不实现DRAM array/controller或NoC。

## 架构与同因对照

从既有H/plus几何提取同一memory经ports 0/2/3到三个不同compute的合法overlap边。
它们在最小系统中别名为M0、C0/C1/C2。方向选择发生在source侧、第一次HB之前。
只提取实际connector交集作可达证据，不运行wafer LP，不把接收端变成转发router。

主候选固定Home256/D1、Shared160/D2。比较独立Home/Left/Right TX与
Home/可配置Shared TX，保留两个物理Shared方向和三个独立RX。所有接入宽度相同。
本轮HB为零链路延迟数字beat连接；没有长线credit往返、工艺映射或实际时钟频率结论。

native输入为valid/ready、完整256-bit data、HOME/SHARED role；目的方向metadata来自外部映射。
独立基线支持按字选择两个方向，可配置结构只接收与冻结cfg一致的Shared目的地。
测试实例整个epoch只有一个Shared方向，两种配置分别验证；运行期间不切换伙伴。
RTL内部没有流量sequencer。source必须在valid未握手时保持data、role、direction。

## 完整字与握手

复用已有 `cse_fifo/cse_packetizer` 的整字准入和跨字packing；深度仍含正在串行化的字。
每个实际TX另加一个明确计费的elastic beat寄存器，满足valid/data/units在停顿时保持。
可配置版本在共享TX的beat寄存器之后静态选择方向；独立版本有两个Shared beat寄存器。
这不是把新增存储藏在D中：结果单列whole-word FIFO与beat holding存储。

HB beat携带payload、valid、有效32-bit单位数，接收端提供ready。单元数为
gcd(256,width)/32的整数倍；有限流尾即时发出部分beat，不等待下一个完整word。
RX为每条物理边的有序reservoir，容量为 `256+width-gcd(256,width)` bit，
含可能被compute反压的完整word；不得把RX临时状态算成免费。
无需跨bank仲裁/reorder，因为本轮每个physical stream只有一个原生源。
debug tag编码于synthetic payload低32bit，scoreboard以原始输入索引独立核对；
这不代表真实request ID无需传输，后续汇聚需额外协议与成本。

第一验收标准：每个已接受的(tag,destination,payload)在正确RX恰好恢复一次且有序。
每槽检查源接受位数 = RX已交付位数 + TX/FIFO/beat/RX中剩余有效位数。
正在FIFO内保留但已发送的字前缀不能再次计入pending位。
另外检查FIFO/reservoir界、native/HB/RX的hold、未选方向静默、配置epoch固定。
使用Icarus支持的时钟采样检查与`$fatal`，不是声称已做形式SVA证明。

## 固定验证集合

- 主B：两方向 × home/shared/mixed/native-burst/random-stalls/long-stall/finite-tail，14条成对轨迹。
- 回归：Shared128/D1、192/D1、192/D2、256/D1，各shared/stalls/tail，12条成对轨迹。
  这些是gearbox测试，不冒充四种完整系统架构/PPA比较；Home仍为256。
- 每条轨迹两个架构同时运行，native word序列、外部offer机会和三个RX的ready完全一致。
  同时比较每槽准入、HB和RX输出，任何性能差异均报失败，不靠不同随机输入作对照。
- 每条长轨迹10,400个word；tail为17个shared word，覆盖非整beat结束。
  饱和服务在1,040槽warmup之后测8,320槽，以Python周期执行作为独立速率参照；
  有限边界允许每方向至多1个完整字误差。所有已接受字最终全部排空并逐bit核对。
- 两个负例检查器：中途改变cfg、在scoreboard注入payload单bit错误，必须触发指定失败。
- 覆盖native、HB和RX停顿，记录stall计数；不靠任意随机种子宣称容量区间或实际DRAM时序。

本轮26条成对功能轨迹、2条预期失败检查，无Yosys/OpenROAD综合、无wafer LP。
如果发现协议导致吞吐低于旧模型，如实记录并修复/定位，不能放宽服务断言掩盖差距。

## 成本与复现

报告主B每个source slice连同三个物理RX的FIFO、held beat、RX payload和控制寄存器位数；
data lanes与valid/units/ready单独登记。未选RX仍按制造模板计费。
这是声明状态位，不是面积、频率、功耗，不能与旧pipeline proxy重复相加。

运行地点为eex005既有隔离检出，单线程；source必须先提交且工作区干净：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m w2w run_shared_egress_rtl --roundtrip \
  --tools memory_results/cse_tools --output memory_results/endpoint_roundtrip_<source>
```

记录源码号、工具、物理边、输入trace/hash、每例计数和失败检查日志。
通过本轮只证明这个同步数字接口的功能与所测持续吞吐，下一步才讨论局部PPA是否值得做。
