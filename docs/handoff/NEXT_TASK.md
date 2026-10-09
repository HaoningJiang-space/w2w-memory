# 当前任务：独立 RWDL 原生服务域与瓶颈迁移

坐标几何和有限流式返回已在固定 `c2_b4`、4-way 完整层执行：整包
1,055.534 μs，流式 1,064.328 μs；流式本次慢 0.83%。
[结果与执行边界](../reports/WAFER_MACHINE_CLOSURE_REPORT.md)。旧九项驻留结果保持冻结。
不继续优化 endpoint，不扩大驻留 DSE，不先增加 Direct HB。

下一项只落实[机器闭合合同](../methods/WAFER_MACHINE_CLOSURE.md)中的原生组织：

1. 保留 Ramulator 的命令/刷新框架，以 32 个独立 128-Mbit、128-bit RWDL 域构造
   每 M 512 MiB 的显式候选。区分公开容量/接口数据和自定阵列时序；不能把 HBM2
   带宽直接乘倍数。扩展源码和 CMake/codegen 配置都进入 `w2w/service/dram`。
2. 明确 16 B 原子传输、整数 3760 ps 时钟、CDC、命令队列、刷新与有限返回存储。
   保持逻辑地址/32 B 字、4 KiB descriptor、MC32 和 requester32；按 offset 对应
   两次原子传输。独立域的 command queue 不能因默认值被静默复制 32 倍。
3. 明确 RWDL 与 HB 是否为同一组物理数据通道，记录每域/每 M 的 lane 和共享资源。
   32×128-bit 独立通道不能仍沿用旧 Home HB 的 2048-bit 标牌而不解释汇聚。
   Controller-ready 边界不得免费产生 pre-HB 的直接分叉。
4. 同一个四 token/4-way 完整层，对照已完成的 HBM2＋新几何＋流式返回。
   只观察原生并行度改变后是否出现 NoC/HB/窗口瓶颈，并分别列资源；不将不同
   原生组织的时间比当作同硬件加速。不重写 kernel 或重启 BookSim 验收 campaign。

**所有仿真工具修改统一在本仓库维护。** 优化 BookSim 的补丁、在线 C++ 接口和
Python runtime 已内置；`tools/build_native.py` 从本仓库在隔离目录重建网络/DRAM
bridge。新运行不依赖另一位开发者的 `wafer_simulator` 工作区，参见
[独立构建](../methods/NATIVE_TOOLCHAIN.md)。第三方原始 Ramulator 保持锁定；构建物、
环境、原始 captures/events 留在 Git 外。

实验只在 hn072 的 `/Projects/haoning/w2w-full-system-*`，源码经 Git。旧工作树
`w2w-full-system-closure-20261009/source` 固定为执行源 `a9066bc`，结果与配置不得覆盖。
RTL 和其他开发者目录不动。旧任务见[历史索引](NEXT_TASK_HISTORY.md)。
