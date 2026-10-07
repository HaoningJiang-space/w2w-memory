# 开发交接：Wafer-scale Memory Service Fabric

**当前运行入口已统一：** 从[真实 trace 工作流](guides/TRACE_WORKFLOW.md)开始，
区分归档审计、服务器原始输入复核和完整重跑。下载公共逻辑归入
`workloads/patterns_download.py`，单样本 CLI 默认 HF 原站；不会自动切镜像或使用 VPS。
根 README 中“暂无真实 trace”的旧状态已更新。历史实验及旧命令保留，不改旧结果。

**2026-10-07 真实 trace 流程完成并整理代码：** 48/48 注册回放、1,094,980,608 个完整模拟读字
全部核对；原始 routing → 专家 union → 完整权重读 → endpoint/HB/RX → 完成时间已接通。
三个互不重叠的 request 组，各测嵌套 batch1/4/16；所有窗口及无收益结果都归档。
63 项定向测试通过。代码整理后七设计身份不变，48 份审计与 CSV 在两端复核一致。
[结果与复现](reports/PATTERNS_REPLAY_STUDY_REPORT.md) / [模块入口](CODE_STRUCTURE.md)。
这是 routing 驱动的读阶段模拟，不是端到端 MoE 加速；不自动继续扩 RTL 或 DSE。

**2026-10-07 服务器工作流统一：** 本地开发，推送 `HaoningJiang-space/w2w-memory` 的 main，
服务器 `/Projects/haoning/w2w` 通过 GitHub SSH 拉取后执行。完整 Git 源码和历史归档已 clone，
原始 trace 与 ASIC 输出保留原路径并提供入口。Codex CLI 0.161.0 已安装，尚需用户登录。
HF 实测直连快于 VPS，默认直连。见[运行与交接说明](operations/HN072_RESEARCH.md)。
48次真实 routing 多窗口回放已完成，按上面的结果报告和验证记录交接。

**2026-10-08 请求供给成本：** [必要界与最小窗口实验](reports/REQUEST_WINDOW_STUDY_REPORT.md)
完成37测试、502回放、29组同服务消融。冻结接口、布局和仲裁，B以N192保持此前N512的
60槽分散任务完成；同60槽目标，宽k3只需N148，揭示lane/wire与请求状态的交换。
三个主场景的共同最小N为Home96、k2 112、宽k3 192、A160、B192；k2缩窗会损失单热点和
长尾加速，不能将它当作充分供给强基线。请求entries尚未换算metadata面积，无新增RTL。
源码`7663f36`，eex005隔离运行；[协议](methods/REQUEST_WINDOW_STUDY.md)。

**2026-10-07 输入闭环扩展：服务器直接取得 256 个独立真实 requests（849 MB）。**
新 CPU 工作区 `hn072@143.89.78.72:/Projects/haoning/w2w-trace-20261007`，无需 GPU。
批量分析覆盖 batch=1–128；完整权重的 batch1/batch2 读窗口连接到 endpoint/HB/RX 回放。
见[本轮结果、正确性与复现](reports/PATTERNS_BATCH_STUDY_REPORT.md)及[固定研究协议](methods/PATTERNS_BATCH_STUDY.md)。
低 batch 有空间空闲，但固定伙伴的互补大部分由稀疏性解释；大 batch 复用提高、共享机会降低。
原始 routing 保留服务器，不进 Git；下面单 request 记录为此前阶段，不再代表最新覆盖范围。

**2026-10-07 输入侧新增：真实 Patterns Behind Chaos 路由适配器。**
已通过授权原站取得一个 Qwen3/MMLU request（2.51 MiB），Git blob身份与SHA256核对通过；
94层、128 decode步格式验证，单层4步转换成冻结专家权重需求并投影到七个既有设计。
原始路由是真实记录，batch/权重冷读/compute映射仍是显式建模；没有应用加速结论。
[接口与命令](methods/PATTERNS_TRACE_INPUT.md) / [来源与验收](reports/PATTERNS_TRACE_INPUT_REPORT.md)。
Token与raw数据不进Git；无需全199GB下载。以下保留此前各阶段的历史状态。

**2026-10-07 有限任务实验完成：** [77 次冻结回放](reports/FINITE_READ_STUDY_REPORT.md)、49 测试，
22 组 duplicated/configurable 服务一致。分散热点 B 为 77 对 Private 88 槽，扩大请求窗口后为
60 槽；相邻热点、全忙与阶段移动无明显收益。k2 在所测单热点/长尾中仍是强成本参考。
时间为机制模型原生槽，不与 2 ns ASIC 面积合成系统 PPA；下一步是有来源的实际读阶段。

**2026-10-07 系统侧：逻辑读任务导入与回放 infra 验收完成。**
用户确认暂无指定 trace；按[回放合同](methods/READ_WORKLOAD_REPLAY.md)实现地址到 bank/HB 的
冻结映射、任务依赖、有限请求/返回/RX 与完成时间。复用五个已注册 H/plus 候选，加 A/B
两组 configurable 消融；44 项测试通过，三个输入入口七设计结果一致。
源码 `55d4d56`，见[验收报告与归档](reports/READ_WORKLOAD_INFRA_REPORT.md)。
合成任务用于验证，不声称真实 MoE 收益。硬件工作独立保留如下。

**2026-10-07 当前：source 物理修复与共同 Home RX 特化完成。**
同库、2 ns、同 I/O 合同，提取后 source 21,987.294→15,318.674 μm²（−30.33%）；
计入相同特化 Home RX 与两套 Shared RX，总计 −14.49%。所有块及通用 Home 对照通过
本轮 setup/hold、电气与路由器 DRC；最终物理网表完整轨迹回放通过。
方向复用节省 6,668.620 μm²，Home RX 共同特化另省 6,075.174 μm²，分别归因。
没有新增 dual-leaf，不再扩 RTL 支线；回到系统服务—完整路径成本。
见[最新报告](reports/ENDPOINT_ASIC_SLICE_REPORT.md)末节与[当前任务](handoff/NEXT_TASK.md)。
以下为历史交接记录，其中未修复百分比和下一步安排均按各自版本解释。


**2026-10-07 当前定位：架构贡献与 RTL 验证分开。**
主线是 wafer-scale DRAM 服务共享；静态可配置 source egress 是关键机制，
gearbox/FIFO/RTL 是功能与局部硬件成本证据，不另立贡献。
见[研究范围](RESEARCH_SCOPE.md)和[当前任务](handoff/NEXT_TASK.md)。
同库同约束的 [ASIC 单 slice 报告](reports/ENDPOINT_ASIC_SLICE_REPORT.md)已完成，
source 面积减少 35.6%，计入相同三个 RX 为 16.3%；该报告保留修复前的 hold/cap 违例。
仅收尾已启动的网表修复，随后回到整片系统服务—成本归因，不自动扩展 RTL 支线。
以下保留历史阶段状态，其中“下一步”“尚无 PPA”等均按各自版本解释。

**2026-10-07 当前：source-side TX→HB→RX最小闭环通过。**
[最新结果](reports/ENDPOINT_ROUNDTRIP_REPORT.md)，源码 `2745632`，eex005：
26条成对轨迹，逐周期等价；每个架构208,102字逐bit恢复，含背压、有限尾部和192-bit回归。
加入held beat和三个RX后，B的payload存储2,880→2,208 bit；lane不变，尚无PPA。
用户最新要求已将此前RTL暂停范围收敛为这个最小功能验证，未恢复wafer实验或DRAM RTL。
下一步只判断single-slice局部PPA；见[当前任务](handoff/NEXT_TASK.md)。下面为历史状态。

**2026-10-07 最新安排：架构先于RTL，停止继续综合扩展。**
[三组织比较与决策](reports/SHARED_EGRESS_ARCHITECTURE_DECISION.md)记录独立出口、共用FIFO、
共用FIFO＋发送器。补充源码 `3c60583`：23测试、126 LP，服务保持；lane/接入长线不变。
存储收益计入pipeline后只有4.54%/7.45%，局部选择器成本仍需判断。
已提前完成的小型endpoint RTL/通用门实验保留为探索附录，没有面积、频率、功耗结论。
当前只推进模型上的服务—成本取舍，待架构值得继续后再恢复minimal RTL/PPA。
最新安排见[当前任务](handoff/NEXT_TASK.md)，下面保留历史阶段状态。
最新接口核对见同报告§5：gearbox已有TX原型，但ready/valid停顿稳定、RX重组及其成本尚缺；
logic-side落点需重新检查跨reticle可达性。未来验证聚焦这些假设，当前不扩RTL。

**2026-10-07 最新研究收敛：Configurable Shared Egress。**
冻结布局的共享方向已进入显式实现，A/B 在相同服务下节省 33.3%/40% endpoint 存储；
7 设计、441 LP、22 测试通过，源码 `7604acb`。见[接口报告](reports/CONFIGURABLE_SHARED_EGRESS_REPORT.md)。
下面架构竞争是其前置证据；之前“先做逆向综合”的安排已由用户最新要求替换为具体接口
实现与成本对照，暂停新的 matching/cycle、任意 k、深 FIFO 和 DSE，见[当前任务](handoff/NEXT_TASK.md)。

**2026-10-07 前置阶段：工程整理结束，固定 H/plus 架构竞争完成。**
见[最新报告](reports/ARCHITECTURE_COMPETITION_REPORT.md)：161 个合法候选、54 个实际设计、
3,402 个 LP；home/k2/k3 均有 Pareto 区域，wire 预算可翻转 k2/k3 的胜负。
实验源码 `806fe82`，eex005 隔离目录 `/home/wangziheng/Video/w2w-interface-20261007`；
本地 `/home/abc/jhn/w2w-memory`，研究 remote 为 `origin`，隔离服务器为 `research`。
四个模型边界与前轮结果见 [Design API](DESIGN_API.md)、[角色接口报告](reports/ROLE_INTERFACE_REPORT.md)。
该阶段之后已转入上面的具体接口候选，当前步骤以[下一任务](handoff/NEXT_TASK.md)为准。
下面保留前阶段交接快照，其版本、路径和“下一项”均为历史记录。

**交接日期：2026-10-07。读这份文件即可接手，不需要重新阅读整段聊天。**

## 1. 一分钟了解项目

研究目标固定为：**在 wafer-scale Memory-on-Logic 中，联合组织 DRAM 服务接口、WoW 物理连接和静态数据布局，使已有但闲置的 DRAM 服务能力能够被其他 compute 有效利用。**

现在已有可复用的几何、固定数据服务 LP、接口执行模型和多个布局/共享算法。最新阶段完成了“接口实现 → wafer 服务 → 有限目录设计选择”的小闭环；还没有完成通用、等成本的联合综合器。

下一项开发是：**让 home-only、k2、k3 exposure 在相同服务合同与成本账本下竞争。** 不重新做更多 cycle，不单独继续扫 FIFO，不把 endpoint 微架构变成另一个题目。详细任务和验收标准见 [NEXT_TASK](handoff/NEXT_TASK.md)。

## 2. 仓库、版本与工作区

| 项目 | 交接位置/状态 |
|---|---|
| 私有研究仓库 | https://github.com/HaoningJiang-space/w2w-memory |
| 唯一维护分支 | `main`；用户明确要求只维护一个分支 |
| 已验证结果与代码基线 | `3fadebefcb3b2ad54de63f705552b141aed744d3` |
| 最新实验实际源码 | `8b27f7b135718931da9b579272ed7d21285ae81f` |
| 目录重构提交 | `b2811c2` |
| 本地工程 | `/Users/haoning/project/w2w/nw-design-for-wsi` |
| 实验工程 | `wangziheng@eex005:/home/wangziheng/Video/w2w-memory` |
| 最新服务器原始运行 | `memory_results/contract_selection_8b27f7b/` |
| 本次交接修改 | 文档与环境快照；无算法、参数或旧结果变更 |

上述基线号有意固定；包含本文件的后续文档提交不会改变实验源码号。运行新实验必须记录自己的干净提交号。

已有工作区保留 `origin=spcl/nw-design-for-wsi`，研究仓库为 `research-origin`。不向上游推送，不重写历史，不丢弃别人未提交的工作。新开发者需有私有研究仓库访问权；运行环境、凭据、完整临时结果不在 Git 中。

服务器连接沿用已授权的 PowerIC 跳板（凭据单独交接，不放进仓库）：

```sh
ssh -p 23333 abc@terminal.poweric.ac.cn
# 在跳板内：
ssh wangziheng@eex005
cd /home/wangziheng/Video/w2w-memory
hostname
git status --short --branch
```

以 eex005 为准，不套用其他项目 skill 的 eex004 默认主机。Git 同步和新 clone 的 remote 命名见 [GIT_WORKFLOW](operations/GIT_WORKFLOW.md)。服务器共享使用，运行前查看当前负载，默认单线程并限制少量 CPU。当前工作区的本地登录辅助脚本被忽略，不属于新开发者必需的项目依赖。

## 3. 先读这六个入口

1. [固定研究范围](RESEARCH_SCOPE.md)：目标与三层职责。
2. [代码结构](CODE_STRUCTURE.md)：目录、依赖、新旧命令迁移。
3. [最新选择实验报告](reports/CONTRACT_SELECTION_REPORT.md)：当前最具体的结果与边界。
4. [Endpoint bridge 方法](methods/ENDPOINT_BRIDGE_METHOD.md)：完整字执行怎样接到 wafer LP。
5. [物理可达性审计](reports/EGRESS_REACHABILITY_REPORT.md)：R 与 Y 不能混淆。
6. [下一任务](handoff/NEXT_TASK.md)：不要从历史 Gate 中自行挑一条支线继续。

全部历史导航在 [文档索引](README.md)。早期报告保留当时参数与口径，不能拿不同阶段的数字直接排名。

## 4. 代码从哪里接

| 职责 | 入口/API | 使用注意 |
|---|---|---|
| 重复 reticle 几何及 HB | `w2w/geometry/memory_model.py:MemoryFabric` | 物理 overlap 和共享 port 不能改成免费逻辑边 |
| 当前 H/plus | `w2w/service/guaranteed_service_exchange.py:contoured_geometry` | 固定 36C+36M，5 ports；不要套旧 `PORTS=4` |
| Bank exposure/成本账本 | 同文件 `Channels`、`ExposureFabric` | repeated mask；TB/s、width、wire 与 storage 是不同量 |
| 数据驻留 | 同文件 `StripedLayout`；`memory_fabric_dse.py:FractionalLayout` | 不可变份额及容量约束；对象内 striping 假定访问均匀 |
| 固定数据服务 | `FixedService.solve/full_load_certificate` | 每个实际数据源都必须服务，保留字节等式 |
| Full-bank pair | `w2w/synthesis/service_driven_fabric.py:paired_layout` | 要求全部 bank 可双向暴露及足够端口能力；不能直接套 k2 |
| Endpoint 实现 | `w2w/endpoints/endpoint_execution.py:execute` | 完整 256-bit 字、有限队列、发送、反压、守恒 |
| Endpoint→LP | 同文件 `EndpointFixedService` | `direct` 与 `buffered_envelope` 不同；后者仍是流体上界 |
| 执行回放 | `with_delivered_caps` | 当前要求每个 C–bank 唯一路线，是场景特定回放，不是通用合同 |
| 有限目录选择 | `w2w/synthesis/contract_selection.py` | `catalog/evaluate/choose/study`，16 项完全枚举 |
| 实验驱动 | `w2w/experiments/run_endpoint_bridge.py`、`run_contract_selection.py` | 干净 Git、冻结参数、记录结果 |
| 独立复核 | `w2w/analysis/analyze_endpoint_bridge.py` | 160 条记录的独立配对公式 |
| 测试 | `tests/` | 目前 63 项；目录/哈希/守恒/服务/构造均有覆盖 |

研究扩展都放在 `w2w/`；报告放 `docs/`；精选结果放 `artifacts/`；工作输出放忽略的 `memory_results/`。上游根目录的 `Reticle.py/Wafer.py/System.py` 与 NoC 工具保留；当前测试不要求重新编译 BookSim/Orion。

## 5. 必须保留的第一性约束

- 固定字节：`sum_route f[c,b,route] = A[c,b] * r[c]`。不能让其他空闲 bank 替代该 bank 上的字节。
- Bank native service、endpoint、内部共享资源、memory port、HB edge、compute port/controller 都要计容量；多个出口不能复制 parent service。
- 地址允许走某出口（R），和出口物理上到达哪个 compute（Y），是两个独立条件。
- 同一 memory reticle 的硬件模板重复；实例的数据布局可以不同。不能给每个实例免费生成一个新 crossbar。
- 静态驻留在评估前冻结，无免费复制、迁移；oracle 要单独标注。
- 总吞吐、每活动 compute 均值、P5、common completion 和应用时间不是同一个指标。
- 满载保底不是永恒研究条件，可以做 Pareto，但需要注册并验证，不能事后忽略退化。
- `Channels` 用十进制 TB/s，1 GHz 下 8000 bit/cycle=1 TB/s；GiB 为容量单位。endpoint 的 256-bit native word/slot 对应 1.024 ns，不能把各处时钟归一化混算。

## 6. 当前哪些结论可信，哪些不能夸大

| 阶段 | 已有证据 | 正确定位 |
|---|---|---|
| 几何 degree | 高 radix 不必带来高服务 | 稳定机制观察，不是完整新架构 |
| 固定数据竞争 | 请求依赖的资源必须共同有余量 | 理论基础；matching/cycle 是表示工具 |
| 两路径配对 | 0.8 TB/s 路径下 random9 期望 1.462857 | 受限 reticle 放松模型；不是 1 TB/s 路径的结果 |
| k2 reciprocal | random9 精确期望 1.327731 | 64 connections、约 943.6 mm wire proxy；合同成立的前提下 |
| k3 full-bank pair | random9 1.771429，common 1.264421 | 96 connections、约 1852.2 mm wire、配置 HB 3 TB/s；成本更高 |
| Open DSE | 原预算下未稳定胜过结构化 k2 | 不要把更大 heuristic 搜索当成已证明有效的方法 |
| Endpoint bridge | buffered 恢复并发，不自动创造客户端聚合路径 | 指定完整字执行模型；未校准 DRAM/PPA |
| Contract selection | 相同预算下模型会选出不同实现 | 当前是有限目录诊断，尚未击败宽出口配对 |

最新具体例子：每 M lane bits≤18,432、storage bits≤49,152、满载保底1、random9：

| 选择模型 | 实现 | 执行平均 TB/s | 满载 TB/s |
|---|---|---:|---:|
| 理想容量 | 192-bit D0 | 0.885714 | 0.5，不合格 |
| Buffered 流体 | 192-bit D1 | 1.000000 | 1.0 |
| 执行候选 | 192-bit D2 | 1.385714 | 1.0 |

D2 使用 D1 两倍缓冲，并非等实际成本。若放宽 lane 预算，旧 256-bit D0 仍达到 1.771429，未被新方法超过。

## 7. 复现：先用归档，再跑闭环

从仓库根目录运行。服务器已有 `.venv`，直接复用。新机器建立环境：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-memory.txt
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python -m w2w --list
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m w2w analyze_endpoint_bridge artifacts/results/endpoint/endpoint_bridge_results.json
```

预期 63 项测试通过，独立 bridge 复核 160 条记录。已验证 Python/依赖版本见 [环境快照](handoff/ENVIRONMENT.json)。requirements 是范围约束，不是精确 lockfile。

运行新实验前先提交并保持工作区干净，不删除 runner 的检查：

```sh
git status --short --branch
git rev-parse HEAD
.venv/bin/python -m w2w run_endpoint_bridge --output memory_results/handoff_repro/bridge.json
.venv/bin/python -m w2w run_contract_selection memory_results/handoff_repro/bridge.json --output memory_results/handoff_repro/selection.json
.venv/bin/python -m w2w verify_egress_reachability --output memory_results/handoff_repro/reachability.json
```

桥接预期 64 个 micro traces、160 条 wafer 回放；选择输出 16 个候选、384 条预算/目标/模型记录，包括不可行情况。不要期望 source commit/host 与旧文件相同。只有单线程受控 CPU 即可，不需要 GPU。

LP/ILP：固定布局服务用 SciPy/HiGHS LP；小配置集合划分才是 ILP；最新16项选择是完全枚举。`A*r` 联合连续优化是双线性，不能改名 ILP。

Gurobi：eex005 主 `.venv` 没有直接安装 gurobipy；已通过现有 `moe-chiplet-thermal` 环境的 site-packages 接入，13.0.3 的一变量求解于本次交接通过。历史记录为受限 license，不能据此保证大 MILP 可跑。旧 runner 的 `--gurobi-site` 用法见 [SERVICE_DRIVEN_METHOD](methods/SERVICE_DRIVEN_METHOD.md)。本轮复现不需要 Gurobi，不复制 license 文件。

## 8. 结果与溯源

- [最新结果](../artifacts/results/endpoint/contract_selection.json)：catalog、cost、frontier、所有选择。
- [最新桥接输入 gzip](../artifacts/results/endpoint/contract_selection_bridge.json.gz)：解压 SHA256 对应选择结果 `input_sha256`。
- [可达性审计](../artifacts/results/endpoint/egress_reachability.json)。
- [63 测试与等价性凭据](../artifacts/provenance/contract_selection_verification.json)、[测试日志 gzip](../artifacts/provenance/contract_selection_tests.log.gz)。
- [目录迁移清单](../artifacts/provenance/layout_migration.json)：115 个路径迁移、21 份旧结果保持字节哈希。

服务器旧实验有 13 个目录已逐文件校验后压缩，恢复办法见 [SERVER_STORAGE](operations/SERVER_STORAGE.md)。不要为了清理删除归档、环境或原始证据。本次交接不启动新的后台长实验；接手时仍应检查当时进程，不能假定服务器无人使用。

## 9. 已知限制与常见误用

1. 旧 `Channels.buffer_depth` 只改 `cost()`；有限执行是另一个层，不能改这个参数便宣称模拟了队列。
2. 最新选择的 lane/storage 账本和 `ExposureFabric.cost()` 的旧 buffer/pipeline proxy 不是同一成本公式；后续必须对齐，避免重复收费。
3. `execute()` 当前只支持1或2目的出口；不能默默用于任意 k-way 或非对称带宽。
4. `population_rates()` 针对 disjoint pair，且 single≥paired。k2 分组、多个伙伴和边缘 private bank 不能直接套其18对公式。
5. 在当前 H/plus，每个已用 C–bank 只有一条真实路线；`R=all` 不会增加路线。强制从不可达出口取字节意味着构造不可行。
6. 三种接口/多个宽度是数字实现模型，尚无 PDK、布线完成、真实 DRAM timing、地址级 trace 或校准 PPA。
7. 新选择实验使用指定概率分布的精确期望，无需 train/val。学习布局/伙伴时仍须训练选择、验证调参、测试冻结；不能在测试集重选方案。
8. 前作边界尚未穷尽核对；不要宣称首次 bank sharing、首次 weighted striping、首次 H/plus 或首次 matching。

## 10. 接手后完成标准

先能复现本文件的结果并理解合同边界，再按 [下一任务](handoff/NEXT_TASK.md) 接 exposure 候选。用户希望研究真正有用：如果同预算下没有优于强基线，应明确报告阴性结果及瓶颈，不靠换指标、免费路径或 oracle 驻留制造收益。
