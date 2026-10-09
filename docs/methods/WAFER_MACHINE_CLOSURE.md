# 从可执行系统到有物理依据的 wafer machine

2026-10-09。核查源码 `b0aeb4b`；接续完整 routed FFN 和固定驻留实验。
本文件给出后续实现合同。除下表“现有实现”外，几何生成、细粒度返回和独立
RWDL profile 均是待实现设计，不能引用为已经完成的 simulator 能力。

## 1. 当前结果属于哪台机器

现有系统是 36-channel HBM2 reference + 合成 6×6 stitched compute mesh。
它已经执行有限网络、DRAM 命令、SRAM、计算和完整 FFN 数据依赖；尚未校准成
某个 WoW 制造平台。新物理机器使用新 machine ID，保留旧结果及其输入身份。

| 边界 | 现有实现与源码 | 后续需要改变的合同 |
|---|---|---|
| reticle / tile | `domain/system.py:mesh_system`，整数网格坐标、每 reticle 一个聚合 tile | reticle 外形、µm 坐标、router / MC / HB 落点分开表达 |
| C–C | 每邻接边 10 mm、2-cycle pipeline；native BookSim | 由路径段生成长度、延迟、credit 延迟和成本 |
| 原生 DRAM | `RamulatorAbsolute`，32 banks、512 MiB、两个 pseudochannels/M | 保留 HBM2；新增组织须逐项声明独立/共享资源 |
| HBM2 回调 | controller payload ready，已含原生数据总线 | 不把回调挪回阵列；不能在此免费接 pre-HB 分叉 |
| descriptor | 全部 32 B words 完成才 `native_ready` | 保留 descriptor 身份，增加带 offset 的部分就绪事件 |
| 网络供数 | `BookSimNetwork.try_send` 立即 supply 所有 flits | 分开 admission、部分 supply 和 RX commit |
| 计算 | 明确的 tile 吞吐假设，blocking tiles | 需要目标硬件校准；仍不宣称数值推理验证 |

当前 MC slot 直到全 descriptor 拷入 NI 才释放。流式设计不能只提前释放 slot，
否则会在相同“32 slots”名义下偷偷增加未完成读数和返回存储。

## 2. 第一性约束：数据路径和服务割必须同时存在

每次读依次占用阵列/命令资源、原生数据域、实际跨层路径、NoC 和接收写端口。
对任意共同资源集合的割，必需字节总量除以其可实现服务率给出必要完成时间下界；
任务依赖、排队和行冲突会进一步延长执行。连接边不能复制父资源的服务能力。

因此，机器定义至少同时保存：

- **placement**：wafer 圆、边缘排除区、reticle 多边形/朝向、局部端口坐标；
- **paths**：每条 C–C / C–M 路径的线段、stitch 点、HB 落点与方向；
- **service domains**：每组 banks 共享哪些命令、列总线和返回队列；
- **timing recipe**：线段流水、serializer、CDC、credit 返回和时钟关系；
- **accounting**：运行资源 ID、制造份数、bit-mm、寄存位、HB signal sites；
- **evidence**：每一参数分别标为文献数据、实现测量、建模假设或待定。

路径、时延和成本消费同一份定义。缺失线宽/时钟/服务边界时拒绝运行；面积或能量
未校准可以保留未知，不必为了跑时序而补零。这个层生成已有 `SystemSpec`，不接管
kernel、BookSim 或 Ramulator 的调度。

## 3. 一个具体的几何起点，以及它不支持的直连

先定义矩形 stitched 候选，不继续优化 H/plus。候选采用 300 mm wafer、居中的
6×6 reticle 区域、26×33 mm field、100 µm 间隔、1 mm edge exclusion。
后三项中尺寸沿用公开 WoW 研究的 field 尺度，间隔和 exclusion 是本项目待核实的
设计假设；都不是 foundry design rules。[WoW §3–5](https://arxiv.org/html/2603.05266v1)

每个中心坐标为 `((x−2.5)×26.1, (y−2.5)×33.1) mm`；局部 router / home MC
先置于中心并明确是聚合模型。两层同位置矩形时，HB 落点位于对应重叠区域，
阵列到落点的片内数据路径仍属于 native domain，不以零长度替代。

这组矩形外包络为 156.5×198.5 mm，角点在有效 wafer 圆内；C–C 中心路径水平
26.1 mm、垂直 33.1 mm，不能继续沿用每边 10 mm。如果仅为敏感性沿用公开研究
的“每 2 mm 一周期”规则，分别是 14 / 17 个传输周期，credit 同样计入。
此规则是工程模型，不能称为工艺时序收敛。真实值应由线、驱动、retiming 与时钟确定。

**完全对齐的矩形只有 Home overlap，没有邻居 Direct HB。** B2 必须给出改变后的
memory placement、轮廓或其他合法 attachment，同时计入数据在 memory wafer 内
到 HB 落点的路径。不允许在这张几何图上凭空添加 M1→C0 垂直边。
若保持 no-stitching，完整 compute 通信需要另一个明确的转发平台，不能由 DRAM
端点代替。当前 stitched 候选与原 LoI/LoL H/plus 是不同机器。

具体导出规则：对有向线段 e，`wire_bit_mm = width_bits × length_mm`；数据与 credit
分别记录方向、位宽和延迟。全双工必须各计一份。数据 pipeline 存储取实际注册级数
乘位宽，router buffer 另外计，不能把总延迟直接当作寄存器数量。HB 的 signal sites
由 lane 数、时钟/控制、备用和 P/G 假设决定，overlap 面积仅用于可布置性约束。

## 4. 原生供给的两个有解释的配置

| 配置 | 容量与独立数据域 | 原生峰值口径 | 状态 |
|---|---|---|---|
| HBM2 reference | 每 M 512 MiB，32 banks，共享两个 pseudochannels | 32 GB/s/M；持续值由命令/行/队列决定 | 已执行；保持原 pin 和 controller-ready 回调 |
| SeDRAM-inspired 4-Gbit | 每 M 32 个 128-Mbit 阵列域，各自 128-bit RWDL | `32×128/8×266 MHz = 136.192 GB/s/M` | 组织候选，未实现/未校准的时序配置 |

第二行根据 SeDRAM 公开的独立 128-Mbit channel、128-bit RWDL 和 266 MHz 接口组织
按相同容量推导；论文报告的是其自身芯片，不能把其测量结果当作本项目整个 wafer
的测量。[SeDRAM §2.1、接口时序](https://doi.org/10.3390/electronics12051077)

这条推导保留 512 MiB/M 和 18 GiB 总容量，改变的是独立列数据域及其控制/布线。
它不是把 HBM2 channel 带宽乘四：必须重新给出每域命令状态、刷新、行/列时序、
地址映射、MC 分布和有限返回预约。继续用 Ramulator 的框架表达这些资源；公开资料
不足的时序先列为假设/范围，不用 HBM2 的所有常数冒充 SeDRAM。

136.192 GB/s 仍低于当前声明的 256 GB/s Home transport；一个 compute 从四个域群
读数据时，聚合供给却可能超过其 NI/RX。瓶颈应按实际路径及活动字节分析。
同组织、同频率若要达到 1 TB/s，需要至少 235 个这样的 channel，容量也随之超过
29 Gbit；若仍坚持 4 Gbit，则必须改变阵列划分/频率等物理设计，不能只改带宽字段。

## 5. HB 的位置需要两种诚实的表达

**保留 HBM2 的参照路径：** native callback 已在 home controller；下游只执行
NoC/DMA。另加一条 link 只能称为 callback 之后新增的 transport，不能冒充原本
已含在模型中的那段 native bus。此配置继续用于驻留和系统反馈研究。

**RWDL→HB 的候选路径：** 阵列 wafer 的独立 RWDL ready，在不可撤销读发出前已
预约有限输出存储；随后经唯一对应的 HB/data path 到 logic wafer 的 MC/NI，再进入
compute NoC。B1 与 B2 共享同一阵列命令/列数据资源，分叉位于显式数字端口之后。
若 RWDL 与 HB 实际是同一条并行数据通道，只计一次传输资源，不能画两个串联的
同速总线各收一次序列化。若确有 gearbox/汇聚，则分别记录新增阶段和存储。

控制器可位于 logic wafer；命令由它到达阵列，直接返回目的地仍受唯一控制器管理。
不能为多个 compute 各复制一份 bank controller 或一份 native 峰值。

## 6. 先修正返回粒度，保持其他实验因素不变

当前适配器只把 native ticket 映射到 descriptor ID，等该组所有 words 完成才回调。
拟增加 `WordReady(request_id, byte_offset, bytes, ready_ps)`，ticket 同时保存 offset。
保留现有 4 KiB descriptor、32 outstanding、MC32、原始地址和请求头数量，网络仍是
同一持久 BookSim。旧 `descriptor_complete` 模式作为显式对照保留。

最小流式策略采用有限重组与按包内顺序供数：

1. 每个已接纳 descriptor 预约至多 4 KiB payload 槽及 readiness bitmap；native
   回调可能乱序，按 offset 标记，不能用“累计完成数”假定连续前缀已经可发送。
2. NI 可以拒绝 admission；尚未接纳时数据留在已预约的 MC 槽，不能进入无限队列。
   接纳只创建消息，不等于 payload 已全部就绪。
3. 第 j 个 flit 覆盖 `header + payload` 字节流中的确定区间。只有该区间涉及的
   所有 native words 就绪，且前面的 flit 已获 supply，才追加供数。256 B flit 和
   16 B header 导致 payload 边界不总与 32 B word 对齐，必须按区间覆盖核对。
4. 本地返回也从同一 ready 区间驱动 DMA；不能让 Home 等整包、远端却能流式。
   每个 flit 经过现有有限写端口后 commit，任务仍等全部必要字节交付才解锁。
5. MC payload 槽只在其所有字节的保管责任转移到有限 NI 后释放；requester
   outstanding 仍在最后接收时释放。MC、NI 的复制/共享存储关系显式计费。

这一步消除“最后一个 word 阻塞整个 descriptor”的部分屏障，仍保留包内乱序形成
的前缀等待。若要允许任意片段独立返回，须另计标签、headers、重组与仲裁；本轮
先不改变包格式，也不同时设计新 MC 排序。流式返回可能改变后续 admission 和行
访问顺序，不能从旧日志离线减去一段延迟就宣称新性能。

## 7. 下一次只做可归因的模型更新

先收齐并归档 Home/Pair/4-way 三个 cohort 的旧模型结果。其结论只属于上述参照机器。
随后按顺序交付：

1. **机器定义到 SystemSpec 的导出**：检查圆内放置、端口/overlap、同一线段的
   latency/credit/cost，输出新 machine ID；先保留同样 36 个逻辑 owner。
2. **HBM2 的有限流式返回对照**：同图、同地址、同源端窗口和包格式，比较整包/
   前缀流式；保留原生就绪、首次 supply、最后 commit 时间以解释变化。
3. **独立 RWDL profile**：先落实上节缺失时序/资源，再接同一 FFN；HBM2 和新
   profile 各自报告，不把不同原生服务预算的差值归因于 attachment。

每一步沿用日常回归并检查其新增因果合同，不重新开展 BookSim 验收。现有 kernel、
native 网络、DRAM bridge、routing 输入和 RTL 均继续复用。
在这些边界闭合前，不扩驻留 DSE、不把额外 Direct HB 或 configurable 定为赢家。
