# RWDL 原生服务与固定完整层比较

候选实现位于 `service/dram/rwdl_spec.py`、`rwdl_refresh.cpp` 和
`memory/rwdl_backend.py`。复用锁定 Ramulator 的命令、行状态、FRFCFS 和完成框架，
新增标准 `W2WRWDL`，不修改上游源码，不复制 HBM2 时序或乘带宽。

## 接口与假设

[SeDRAM §2.1、§3.1](https://doi.org/10.3390/electronics12051077) 给出独立
128-Mbit channel、128-bit RWDL、3.76 ns 时钟和约 6 ns CASRD→RWDL。
本研究按相同阵列单元扩至 32 channel/M，共 512 MiB；不是制造的 WoW 产品。
整数 3760 ps 对应 265.957 MHz，读接口峰值为 **136.170 GB/s/M**。
RWDL 与 HB 是同一组 4096 条双向数据 lane，读路径只计一次数据传输。

每域一个 array/bank、一行 64 个 16 B column、16384 行。原来 32 B 逻辑字与
bank interleaving 保留；每字的低/高 16 B 在同一域进行两次列访问，不能免费拆分。
每 bank 一行仍对应 32 个逻辑字，保持与 HBM2 地址映射的行容量可比。

| 参数 | 周期数 | 说明 |
|---|---:|---|
| data beat | 1 | 128-bit / 3760 ps |
| CAS latency | 2 | 将公开 6 ns 向上取整到 7.52 ns |
| callback latency from RD | 3 | CAS 后包含一整个 beat，11.28 ns |
| ACT→RD / PRE→ACT | 4 / 4 | 假设，各 15.04 ns |
| ACT→PRE / ACT→ACT | 9 / 13 | 假设，33.84 / 48.88 ns |
| RD→PRE | 2 | 假设，7.52 ns |
| refresh busy / interval | 43 / 1037 | 假设，161.68 ns / 3.89912 μs |

除接口锚点外，阵列、写恢复和刷新参数都只是明确的研究假设。32 域独立命令与
刷新，无额外共享 ACT 电源限制；跨域电源/热耦合未标定。每域一条命令总线，
ACT/PRE/RD/REF 共用该域一命令/拍机会。不能把候选时序当作实测 SeDRAM。

## 数字资源与返回

每 M 共 32 个简化 Ramulator channel controller，资源显式列账：

- 每域 1 个 read queue entry，共 **32**，没有默默变成 32×32。
- 每域 1 个 active entry 和 1 个 refresh priority entry，各共 32。
- 每域 1 个 write queue entry，共 32；本轮无写流量。
- 共享 descriptor admission 仍为 MC32，返回空间为 32×4 KiB = 128 KiB。
- 每域最多 8 个 reserved atom，共 256 个/4096 B。读接纳前预约，直到 CDC
  和汇聚输出结束才释放；约束包含 controller pending、原生在途和 CDC/FIFO。
- 同一 MC dispatcher 每个原生拍最多展开 32 atom，各域最多 1 个；域内 descriptor
  FIFO，域间独立 cursor。元数据最多 32×32 个 descriptor/channel 引用。
- 原生 tail 向上采样到 1 GHz NoC 边界，再经过 2 个 NoC 拍的 CDC。
- 每 M 共享汇聚出口 **2048 bit / 1000 ps**，即 256 GB/s；所有域争用，未
  服务的 atom 留在已预约的有限空间内。CDC/FIFO 共用上述 4096 B 预约预算。
- 连续 byte prefix 交给现有 finite streaming NI；计算仍等待完整 tile 读取。

网络 SystemSpec 中的 Home HB link 是旧 controller-ready 模型保留的结构占位，
本后端不在该 link 发包，**其 2048-bit/1GHz 标牌不代表 RWDL/HB 数据接口**。
成本记录必须用实际 4096-bit/3760ps 接口替换占位 HB，C–C 段保持原样。
控制/地址线数量、数字 controller/mux 的物理面积和能耗未知，明确记为未标定；
只报告 data lane、buffer、pipeline 等资源，不声称真实 PPA。

## 时间推进与实验

`time_advance='boundaries'` 只改变既有 kernel 的循环采样点：跳到下一时钟边界、
任务 release/finish 或已安排事件；保留所有原有执行阶段顺序。默认 `gcd` 模式保留。
混合时钟小任务应逐事件对照两个模式，避免 40 ps 空转使完整实验膨胀 25 倍。

`python -m w2w.experiments.run_rwdl_study --prepare --output <new-directory>` 冻结
`c2_b4` 四 token、全部 expert owner 和两个布局；先检查 4-way 图与归档 HBM2
streaming 输入完全一致、共同机器仅 DRAM 周期不同，并检查 Home 的逻辑工作一致。
运行 `rwdl-four_way`、`rwdl-home`，HBM2 A 不重跑。完整数据/事务/SRAM 事件独立审计，
原生 atom 数、reservation 和 pending 单独守恒。

只有实际执行显示网络限制后才增加有成本账本的宽 NoC 诊断。不同 DRAM 组织之间
的时间比是架构比较；无 direct HB、无 endpoint 改动、无计算预取、无额外 DSE。
