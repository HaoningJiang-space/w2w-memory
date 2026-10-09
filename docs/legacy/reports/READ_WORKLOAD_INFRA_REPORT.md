# 逻辑读任务导入与回放 infra 验收

2026-10-07；执行源码 `55d4d56f1ccc89f9a1b7f98a2d5a2812376b25e6`，eex005 干净隔离目录
`/home/wangziheng/Video/w2w-read-replay-20261007`。

**交付完成：同一逻辑读任务可以经各自冻结的合法地址布局，在 Home/k2/k3 上做依赖回放；
A/B 的 duplicated/configurable 可以做同请求、同服务消融。** 用户确认暂无指定真实 trace，
本轮只验收可复核的 infra。以下数值全部来自明确标记的合成任务，不是 MoE 应用结果。
另一开发者的 RTL、约束、硬件结果未被这轮实现修改。

## 新增了什么

- `read_trace.py`：完整字对象、地址区间、发起时刻、依赖、读后计算和完成条件；拒绝越界、
  未对齐、错误 owner、重复 ID 和循环依赖。
- `read_residency.py`：将现有份额编译成固定字条带，给对象分配互不重叠的 bank 内地址；
  检查所有常驻对象的容量和合法 HB 路径。按实际地址计算每个任务的 A，不强迫阶段比例固定。
- `read_replay.py`：有限 outstanding、请求延迟、原生供给/返回预留、按位宽发送、有限 RX
  与依赖触发。逐槽核对请求、完整字、bit 和 credit，记录任务完成而非平均带宽倒数。
- `moe_reads.py`：导入单层逐 token 路由；只用训练批冷读量做静态 expert 负载均衡，所有
  结构共用归属。每批相同专家只读一份权重，明确批内复用、批间无缓存及整模型计时边界。
- `run_read_workload`：绑定原架构目录、逻辑 trace、冻结地址、完整 design、配置与成本哈希；
  可附 design-bound 硬件 artifact，保持作用范围、单位、时序状态和 SHA 独立。

接口和执行顺序见[注册合同](../methods/READ_WORKLOAD_REPLAY.md)。验收源码包含早期发现的
零时长 join 顺序修复：先闭合瞬时依赖，再仲裁 compute，避免 join 名称改变同槽任务优先级。

## 验证证据

**44 项测试通过：18 项新增测试 + 26 项相关回归。** 没有重复声称跑过全仓库全部测试。
新增测试包含独立解析完成时间、必需远端字节、160-bit 跨字与尾部、地址唯一性和容量、
不同阶段 A、任务依赖、compute 排队、credit/RX 反压、原生停顿和非法输入/超限拒绝。
已有 design、角色接口及目录/归档回归通过。

七个设计各回放同样的 48 个任务：36 个全活动 expert 读取、8 个稀疏读取、1 个重复 token
所需的单 expert 读取，以及 3 个批末 join。每个设计精确交付 **74,880 字 / 2,396,160 bytes**。
36 个 expert 在训练输入中均衡分配到 36 个 compute；没有从测试活动重选伙伴或驻留。

除 `--demo` 外，将相同输入分别导出再通过 `--trace` 和 `--training-routes/--routes` 运行。
三个入口的七设计结果在 trace/design/residence 哈希、任务时刻、逐路计数、交付事件哈希、
native 字数、停顿和成本上全部相等。另从结果独立核对总字节、逐路 bit 合计、native 字数、
所有依赖的完成先后、读后计算关系及 makespan=max(task finish)。

## 合成任务回归快照

单位为原生 slot；这里一 slot=1.024 ns，是机制模型单位而非实测器件时钟。

| 冻结设计 | 全活动批耗时 | 稀疏批耗时 | 单 expert 批耗时 | 全 DAG 完成 |
|---|---:|---:|---:|---:|
| Home direct | 54 | 54 | 54 | 162 |
| k2 direct，方向 2/3 | 54 | 54 | 54 | 162 |
| k3 full-width direct | 54 | 40 | 40 | 134 |
| k3 A duplicated | 54 | 48 | 48 | 150 |
| k3 A configurable | 54 | 48 | 48 | 150 |
| k3 B duplicated | 55 | 47 | 47 | 149 |
| k3 B configurable | 55 | 47 | 47 | 149 |

每批耗时来自相邻 join 的实际完成差，后批请求由前批完成触发。
k2 在此合成 DAG 中没有缩短总完成时间；B 的有限全活动批还比 Home 多一 slot。
这些回归点说明 infra 能保留不同任务阶段及有限执行的结果，不能替代真实 workload
判断、旧 random9 精确期望或新的最优设计选择。

A/B 两组实现消融均保持任务时刻、逐路交付、停顿、credit 峰值及交付事件 SHA 完全相同。
公共 CostModel 给出每 M endpoint storage：A 为 24,576→16,384 bit，B 为
40,960→24,576 bit；lane、制造方向及接入长线保留。这些仍是模型计数，不是新增 PPA。
新回放所需 RX payload allocation 按完整制造模板另列，A/B 均为每 M 49,152 bit；
request metadata、控制与物理支持面积未知，未压成“总面积”或完整系统 Pareto 优势。

## 与技术基线报告的对应

已读取并校验 [W2W_MEMORY_SERVICE_TECHNICAL_REPORT v1.0](W2W_MEMORY_SERVICE_TECHNICAL_REPORT.pdf)
（Git 归档 `5e06bc0`；28 页含封面）。它给出完整研究目标，本轮 infra 只关闭其中一部分：

| 技术报告要求 | 本轮对应与剩余边界 |
|---|---|
| §2.2、§5.4：冻结地址，阶段 A 可变化，有限对象整数驻留 | 已实现 word 地址、实际容量、任意对齐读区间与逐任务 A；v1 不支持未对齐字节或跨 owner 对象 |
| §6.3、§10.3：请求、原生供给和返回均可追踪 | 已有请求身份、有限 outstanding、bank 仲裁、返回预留及任务完成；尚无地址相关行状态/命令时序、实际控制路径带宽和电路成本 |
| §7.4：长线和反压反馈时延 | 已有有限 RX 与固定前向 link 延迟；反馈返回时延尚未独立建模，不能声称验证了长线 credit 协议 |
| §9.1、§9.3：时钟和全路径实例成本一致 | 已分列模型、局部硬件、制造方向及新增资源；2 ns 与 1.024 ns 尚未闭合，未形成完整系统面积 |
| §10：结构价值与实现价值分别对照 | 已有 Home/k2/k3 及 A/B 同布局消融；暂无真实 capture、DRAM 校准或应用加速 |

PDF §8–9 的 35.6%/16.3% 与未修复 hold/cap 是其读取版本的历史状态。
当前 ASIC 报告末节已给出修复后 source 30.33%、共同特化 RX 口径下局部合计 14.49%；
该更新没有消除上表中的系统时钟、工艺和完整路径成本边界。原 PDF 及 SHA 保留不变。

## 已固定的边界

默认 native 返回延迟为 0，与 always-ready 机制合同一致；请求延迟 1、link 延迟 1，
每 C 每 slot 最多 64 请求字、128 outstanding，每 bank/output RX 深度 2。
非零 native 延迟及反压已有单元测试，但没有真实 DRAM 时序校准。
source 预留模型对非零返回延迟/浅队列是保守的；不能凭该设置认定接口在真实 DRAM 上更优。

这轮模型不执行 payload、RTL held-beat 或电气传播；交付事件相同不等于新增 RTL
逐周期等价证明。已修复 ASIC 结果另见[硬件报告](ENDPOINT_ASIC_SLICE_REPORT.md)末节，其 2 ns
及独立块面积尚未绑定为本回放 1.024 ns 的供给/频率证据，没有拼接百分比。

下一步可直接接有来源的单层路由或逻辑读 DAG，审查缓存、批量与计算依赖语义后再评价
真实等待。固定当前几何和候选；只有观察到具体瓶颈后才改伙伴、比例或路径能力。

## 复现与归档

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m unittest tests.test_read_workload tests.test_design_contracts tests.test_role_interface_regression tests.test_repository_layout -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m w2w run_read_workload --demo --output memory_results/read_workload/results.json
```

两个 JSON 入口的精确命令和对比字段在 manifest；输入完整保存在主结果的 `trace`
和 `inputs.training/evaluation`。服务器还保留原始三份 JSON 输出、输入和日志。
原始结果约 11.4 MB，压缩后约 230 KB；未改写上游架构目录或任何历史实验数字。

- [完整结果](../../artifacts/results/workload/read_workload_demo.json.gz)
- [简表及成本分项](../../artifacts/results/workload/read_workload_summary.json)
- [来源、文件 SHA、输入路径检查](../../artifacts/provenance/read_workload_manifest.json)
- [44 项测试日志](../../artifacts/provenance/read_workload_tests.log.gz)
- [三个入口的执行日志](../../artifacts/provenance/read_workload_runs.log.gz)
