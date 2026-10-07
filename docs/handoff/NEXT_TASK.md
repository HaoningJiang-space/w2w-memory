# 下一研究任务：判断可配置source endpoint的局部PPA收益

研究主线：用较少共享接口硬件，使邻近compute利用已有闲置DRAM服务。
接口方向选择固定在source侧、第一次HB之前；每条M→C必须是合法overlap边。
没有logic侧隐含C→C转发，不实现DRAM array/controller或整个wafer。

## 已完成的最小闭环

[最新报告](../reports/ENDPOINT_ROUNDTRIP_REPORT.md)，源码 `2745632`：
H/plus内提取1M→3C，独立出口与可配置出口共用native word trace、位宽、背压和RX。
26条成对轨迹全部通过，每个架构208,102个完整字逐bit恢复，301,559个成对周期逐槽等价。
native/HB/RX停顿保持、位守恒、容量与错误方向检查均通过，两个注入错误被正确捕获。

主B：Home256/D1、Shared160/D2；RX处测得Shared-only .625 word/cycle，
8:5混合为8/13、5/13，合计1。192/D1=.5、192/D2=.75的gearbox回归通过。
方向配置在epoch内冻结，role与目的metadata由外部地址映射提供，没有endpoint流量sequencer。

加入明确计费的held-beat寄存器与三个相同RX后，payload存储2,880→2,208 bit（−23.33%），
数据lane仍576 bit。尚无面积、频率、功耗或真实链路延迟结果。

## 最近一步

只比较single-source TX＋相同三个RX的局部PPA：同工艺库、同目标时钟和约束，
独立Shared machinery vs静态共用Shared machinery。先核对可用库和工具，再固定运行范围。
保留TX/RX、控制与MUX/gearbox各项归因；不把声明寄存器数或generic gate数写成面积。
若为了时序加入流水/ready往返缓冲，明确新增成本并重验吞吐。

32-bank聚合、真实HB延迟和metadata汇聚在single-slice判断后再做。
原每-M账本不直接加上本轮slice计数，以免重复计pipeline或误算RX制造范围。
private、k2、full-width direct继续保留为系统层强基线，但当前不扩wafer LP。

## 暂停支线

新matching/cycle、任意k、深FIFO scheduler、BO/Benders、placement搜索和真实应用trace暂不扩展。
不继续工程整理。历史架构竞争和slot-credit原型保留原版本证据。
实验在eex005隔离目录执行，源码提交、trace、配置、工具与结果可追溯。
