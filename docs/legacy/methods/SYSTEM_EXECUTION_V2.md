# 完整通信基线：第一版可执行合同

2026-10-09，依据用户给定的完整通信重构方案推进。研究主线改为：在已有 compute NoC 上
建立本地/远端内存强基线，再检验额外 Direct HB。旧读阶段、RTL、LP 和历史结果保留各自范围。

## 当前实现

源码 `19a10b1` 引入独立的 `domain/system.py`、`execution.py`、`protocol.py`，以及
`system/builder.py`、`kernel.py`、`network/router.py`、`memory/address_map.py`、`backend.py`。
它不改变 `MemoryFabricDesign`、`read_replay` 或原 `service/dram` 的语义。
命令标记 `system_execution_v2_prototype`，旧命令默认仍是 v1/endpoint 范围。

- 新平台显式允许矩形 compute mesh 的跨 reticle stitch；memory 仅有到 home MC 的 HB，不作路由器。
- 一个 reticle 暂为一个 tile、一个 engine、一个 MC。记录 reticle/tile/engine 数量；没有免费展开 8 GPC。
- 数据边与控制边分离，图有环、路径不存在、非法同层连接、重复资源 ID、超容量驻留均拒绝。
- 单位 ps；compute、network、DRAM 周期独立输入，kernel 在其公约数时间格协调。
  当前是详细参考循环，尚未做空事件跳跃或大规模性能优化。
- 网络参考使用有限 NI、每类输入缓冲、共享出口、延迟 credit、有限重组存储。
  所有选择先观察当前状态、再提交，不因 Python 遍历顺序穿越多跳。
- task 全工作集预留 SRAM，单 compute engine；输入、权重、scratch、输出均计容量。
  超出 SRAM 的工作要求调用方显式分块。尚无本地 SRAM 读写端口时序或矩阵形状校准。
- B1 请求先到唯一 home MC，预留事务/返回槽后服务；回调只使响应 ready，最终 RX 交付才满足读依赖。
  MC 在数据复制进有限 NI 后释放事务槽，requester 在收到最后的数据后释放 outstanding。
- 地址映射独立于返回路径：对象线性字按 bank 交错，B1 不要求 requester 与 memory 直接 overlap。
- 独立验证从事件重建任务先后、读身份、MC 生命周期、物理链路槽、SRAM 和字节，不调用执行器核算函数。

所有线宽、延迟、容量、计算周期均为显式微基准参数。位宽×流水级数和链路延迟引用同一
`PhysicalLink`，但尚无工艺校准，面积保留未知。原 endpoint RTL/非对称 gearbox 尚未接入 v2。

## DRAM 边界

`IdealBanks`：一个 bank 每 DRAM 周期接受一字，显式延迟后在 memory 侧 ready，再经过 HB。
`RamulatorAbsolute`：复用已有 pinned HBM2 wrapper，slot=1 ps，不从 bank 带宽反推时间。
回调是 controller payload ready，native profile 已包含的数据总线不能再次收费；该模式省去
参考网络中的显式 home HB 请求/返回，不用于 pre-controller Direct HB 比较。
native 缺失必须报错/明确 skip，不回退 ideal 后宣称原生完成。

## 已运行的首个闭环

eex005，2×2 compute、4 memory、3 tasks：C0 计算5周期，向 C1 发128B；C1 从 M0 远端读256B，
计算8周期；向 C0 回64B，C0 计算3周期。每个读事务32B；所有数据交付、credit 和存储排空。
以下数值仅来自该合成合同，不是实际 wafer 或 MoE 性能：

| 变体 | 完成 ps | 路径 flits |
|---|---:|---:|
| B1，N=4 | 97,000 | 79 |
| 所有链路流水和 credit 延迟各加4周期 | 161,000 | 79 |
| B1，N=1 | 246,000 | 79 |
| B0，权重驻留改本地 M1 | 95,000 | 47 |
| 纯控制5＋1周期，无数据边 | 6,000 | 0 |

B0/B1 行改变了合法权重驻留，不是同驻留的 Direct HB 消融。均无应用加速声明。
26 项新定向测试中25通过，native bridge 未提供的一项明确skip。
五项微基准均通过独立事件核验。实际输出与日志另存 provenance。

## 本轮调整后的实施顺序

已完成 R0/R1 和 R2–R4 的小型 ideal prototype，尚未完成生产主后端和完整应用。
用户指出已有加速 BookSim 后，审计并复跑其14项原生接口测试，见
[复用决定](BOOKSIM_REUSE_ASSESSMENT.md)。Python 网络作为参考，不再继续独立扩展。

接下来先把已验证 online/bounded native 接口接入同一任务/事务合同，明确 packet/VC/注入预算
与 SRAM commit。随后验证 Ramulator 绝对时间边界，加入本地 SRAM 端口和显式矩阵 tile。
再导入保留 token 关系的一个完整 MoE 层；B2 Direct HB 和 B1/B2 公平成本比较在此之后。
R5–R7、制造合法 HB 几何、tile 粒度敏感性、完整系统成本与大规模误差均未完成。

```sh
python -m unittest tests.test_system_execution -v
python -m w2w run_system_microbench --output build/system_v2/new-result.json
# 只有已准备 pinned native bridge 与其 Python 依赖时使用：
python -m w2w run_system_microbench --native --output build/system_v2/new-native-result.json
```

代码、构建和测试在 eex005 隔离目录执行；旧大 trace、结果、RTL、第三方 fork 未改。
