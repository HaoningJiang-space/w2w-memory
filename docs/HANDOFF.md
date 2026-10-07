# 开发交接：Wafer-scale Memory Service Fabric

**2026-10-07 最新安排：架构先于RTL，停止继续综合扩展。**
[三组织比较与决策](reports/SHARED_EGRESS_ARCHITECTURE_DECISION.md)记录独立出口、共用FIFO、
共用FIFO＋发送器。补充源码 `3c60583`：23测试、126 LP，服务保持；lane/接入长线不变。
存储收益计入pipeline后只有4.54%/7.45%，局部选择器成本仍需判断。
已提前完成的小型endpoint RTL/通用门实验保留为探索附录，没有面积、频率、功耗结论。
当前只推进模型上的服务—成本取舍，待架构值得继续后再恢复minimal RTL/PPA。
最新安排见[当前任务](handoff/NEXT_TASK.md)，下面保留历史阶段状态。

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
