# 坐标几何与有限流式返回：固定四 token 的完整层结果

2026-10-09；执行源码 `a9066bc`，分析 `1773804`；hn072。
复用同一 kernel、原生 BookSim 和 HBM2，没有重新实现网络或 DRAM 调度器。
所有 W2W 工具修改已进入同一仓库；[独立构建记录](../methods/NATIVE_TOOLCHAIN.md)。

## 结果

固定 `c2_b4`、4-way、全 128 expert 的冻结驻留，380 项任务，
585,248,256 B 权重读取、144,336 个 descriptor、18,289,008 个 32 B native words。
Dispatch、分块权重读取、expert 计算和 combine 均实际完成。下表第一行是已归档结果，
此次没有重跑或覆盖；后两行是同一新机器上的配对执行。

| 几何与返回 | 完整层时间 | 比较 |
|---|---:|---|
| 旧合成 mesh，10 mm / 2-cycle，整包返回 | 1,041.569 μs | 旧九项实验中的四 token 4-way |
| 坐标导出，水平 26.1 mm / 14-cycle、垂直 33.1 mm / 17-cycle，整包返回 | 1,055.534 μs | 比旧配置慢 1.34% |
| 相同坐标导出机器，有限前缀流式返回 | 1,064.328 μs | 比新整包对照慢 0.83% |

**流式返回确实提前供数，但这一次没有缩短整层时间。** 不能把局部重叠直接解释成
应用加速，也不将这个小幅负结果解释成流式机制普遍无效。

## 这次模型改变了什么

`system/wafer_machine.py` 将 300 mm wafer 内的矩形 reticle 坐标导出为 `SystemSpec`。
两层同位置，router/MC 暂用 reticle 中心聚合点；只有 Home overlap。
26×33 mm field 尺度沿用公开 WoW 模型，100 μm 间隔、1 mm edge exclusion、
20 μm / 一周期 HB 与 2 mm/cycle 流水规则为显式建模假设，未做制造或时序标定。

链路的长度、data latency、credit latency 与 wire/pipeline 代理消费同一份定义。
保持 16-flit input VC，不免费增加 credit 窗口。新机器数据 wire 为
7,277,445.12 bit-mm，link pipeline 为 3,956,736 bits；credit 另计
3,553.44 bit-mm 和 1,932 bits。它们不是面积或功耗结果，也不含全部 router/PHY 成本。

`RamulatorAbsolute(streaming=True)` 按 ticket 记录 byte offset；只有连续就绪前缀
可向 native BookSim supply，重复或越界就绪会报错。本地 DMA 同样从前缀供给有限写端口。
保持原 descriptor、请求头、4 KiB 最大 payload、32 outstanding、32 MC 槽、有限 NI/RX。
MC 槽直到全部字节转交给已预留的 NI 才释放；outstanding 等最后交付才释放。
整包模式继续保留。两模式都使用现有有限写端口；整包本地 DMA 一次交付 payload，
流式本地 DMA 按有头部/padding 的 flit 片段排队，短片段仍占一个写周期。

HBM2 回调仍位于 controller payload-ready，已包含原生数据传输；没有再串接同一
HB 数据总线收费，也没有加入邻居 Direct HB。

## 为什么更早供数没有形成更短的层时间

| 观察 | 整包 | 流式 |
|---|---:|---:|
| 全部 native 字就绪前已开始 supply 的 descriptor | 0 | 142,848 / 144,336 |
| 完整 descriptor native-ready → 最后交付，平均 | 63.684 ns | 28.790 ns |
| 最后一笔 native-ready 的全局时刻 | 1,054.178 μs | 1,062.996 μs |
| DRAM read row conflicts，总计 | 818,008 | 860,859 |
| 最忙 C–C 链路的发射周期占比 | 11.86% | 12.18% |
| MC / requester 实测峰值槽数 | 32 / 32 | 32 / 32 |

供数与任务反馈改变了 32 个活动 memory 中 28 个的 descriptor 接纳顺序。
最后 native-ready 晚 8.818 μs，其后的层尾部仅缩短 24 ns，因而没有得到整层加速。
这里报告的是实际事件和顺序变化；未把所有 row conflicts 的增量单独换算成延迟。
平均区间可以相互重叠，不能相加成总 stall。

两项运行的逐 memory 字节相同，峰值仍为 28,318,464 B；以每 channel 32 GB/s
原生峰值得到的必要下界仍是 884.952 μs，约占完成时间的 83%–84%。加上这次几何
与流式结果，当前 HBM2 配置仍未显示显著的瓶颈迁移。链路平均占比不排除瞬时拥塞。

## 单仓库工具与复现

- BookSim 原始 fork、两份优化/hook 补丁、在线 C++ 接口、Python runtime、JSON header
  与许可证均在本仓库。默认接口不再要求外部 `wafer_simulator` checkout。
- `tools/build_native.py` 已从本仓库重建 BookSim 和 bridge。另一次从全新目录 clone
  锁定 Ramulator 后，成功构建上游库和本仓库 bridge；具体 SHA、命令、日志见工具链证据。
- 41 项相关回归通过；干净 Ramulator 构建另跑 12 项相关检查，无 skip。
  完整层两项均结束并排空，独立读取事件重新核对字节、事务、图、地址集、native 配置、
  native 网络输入与二进制身份。没有新开 BookSim 验收矩阵。

```sh
# hn072，从冻结源码 a9066bc 执行；BookSim 使用本仓库构建的二进制。
python -m w2w.experiments.run_machine_closure --output "$W2W_STUDY" --prepare
python -m w2w.experiments.run_machine_closure --output "$W2W_STUDY" \
  --case hbm2-whole --booksim-binary "$W2W_BOOKSIM_BINARY"
python -m w2w.experiments.run_machine_closure --output "$W2W_STUDY" \
  --case hbm2-stream --booksim-binary "$W2W_BOOKSIM_BINARY"
# 分析源码 1773804；分析不重启模拟器。
python -m w2w analyze_machine_closure --source "$W2W_STUDY" --output analysis.json
```

原始完整事件保留于
`/Projects/haoning/w2w-full-system-closure-20261009/study-a9066bc`。
仓库保存[结果和冻结输入](../../artifacts/results/system/machine_closure/analysis.json)、
[交付清单](../../artifacts/provenance/machine_closure/delivery.json)与
[执行网络输入、日志](../../artifacts/provenance/machine_closure/network_inputs_and_logs.tar.gz)。
交付清单的相对路径对应服务器 `delivery` 目录；其中网络日志包归入 provenance，其余
输入/摘要归入 results。原始事件 SHA 在 analysis 中，未把大体积原始事件加入 Git。

下一步仍是落实独立 RWDL 服务域，再用同一四 token/4-way 层观察原生并行度改变后的
瓶颈。它尚未实现，本报告也不包含 Direct HB、制造校准或完整 LLM 结果。
