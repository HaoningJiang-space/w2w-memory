# 历史任务索引

以下建议只适用于各自历史提交；当前工作见 [NEXT_TASK](NEXT_TASK.md)。

## 2026-10-09 完整层执行前的计划快照

# 下一步 完整通信基线与已有 native 后端复用

2026-10-09：以 [SYSTEM_EXECUTION_V2](../methods/SYSTEM_EXECUTION_V2.md) 为当前任务。
已建立 B0/B1 ideal 小闭环；接下来复用 `wafer_simulator` 已优化的在线/有限接收端 BookSim，
先对齐包化、注入容量、VC/协议依赖和 ps 时钟，再验证 native DRAM 事务。
不要继续扩写独立 Python 主 NoC；不要先加 Direct HB、endpoint 机制或搜索算法。
详见[组件审计和14项原生复验](../methods/BOOKSIM_REUSE_ASSESSMENT.md)。

## 以下为此前子系统计划，保留历史依据

研究主线是有限成本下的wafer-scale memory service provisioning。先读[81次新请求结果](../reports/COHORT_REPLAY_REPORT.md)和[wafer/DRAM第一性约束](../methods/WAFER_DRAM_SERVICE_PRINCIPLES.md)，再结合[强基线](../RESEARCH_STATUS.md)选择配置。原生命令接口已接通，不重复开发后端。

## 已完成 不重复开发

- 真实routing导入、冻结读任务、166次独立请求回放与逐字审计。
- bank-local configurable source及局部RTL/P&R；不是跨bank engine pool。
- 本轮新增六项同库映射、28项配对mapped回放：固定专用source更小，可配置source以约4%面积开销保留部署方向选择。
- cohort owner的81次独立请求回放已在eex005完成并审计，九组C duplicated/configurable服务相同；报告与全结果已归档。
- 公开HBM2后端与8次完整对象探针保留为可选验证，不用于当前性能排名。
- 同一HBM2/B接口的两次比例诊断已完成，1/2比8/13少17.44%完整对象读时间；不与旧slot排名混用。

## 完整系统声明前先明确通信路径

新增拓扑审计确认：当前没有C–C通信执行，也没有经memory wafer转发。C–M图连通只表示几何关系；81次结果仍是直接权重读子系统。先在架构图明确compute消息走哪一层、何种router/链路，以及能否与远端memory访问共用；不要把“第一次HB前选向”推广成所有WoW的硬性要求。

后续原生比例诊断仍可作为子系统实验，但不得把它命名为完整wafer或MoE时延。`audit_topology_scope`给出可重跑反例和源码身份，详见[当前状态中的审计](../RESEARCH_STATUS.md)。

## 当前结果决定的下一项设计

下一次先固定同一DRAM原生profile、几何、接口和请求预算，保留既有owner及合法pair，
对照旧比例与原生供给匹配比例，并单独核对请求/返回容量限制。Home/k2保持相同原生预算。
诊断窗口提前登记，已经看过的窗口用于机制定位；若以后重新训练owner，另划验证和测试，
保留modulo、边际LPT及共同owner对照，不回用已发布的新请求成绩选型。

输出每个窗口的完成时间、负例和成本分项，而不是只报同owner Home上的平均speedup。wide不是full pooling；固定专用、未裁剪duplicated、configurable也不是同一服务范围。若不改变硬件而改善owner，必须单列其贡献。

已有[冻结cohort回放协议](../methods/COHORT_REPLAY_STUDY.md)及完整81次结果，**不再次启动同类批次**。
该批是Home/k2/wide/C与LPT对照，不能改称B实验、modulo对照或完整成本比较。
Home/k2本轮映射九窗持平，C两窗改善，宽k3有退化；各自cohort布局下C六窗快于Home。
固定合同的执行距离必要资源下界最多11槽，继续调仲裁缺乏明显空间。

下一项应固定一个明确原生组织，联合安排其服务域字节份额与请求/返回容量：先标出独立
RWDL或共享数据总线，再检查每域速率×占用寿命。用完整多对象读诊断原生竞争与返回预留，
不从当前新测试结果反向调owner。HBM2两次比例结果只是已完成的单对象依据，不能外推整批。

当前已有`synthesis/cohort_placement.py`、`theory/cohort_service.py`和训练探针，先复用，不增加新优化框架。训练、冻结、测试分开；需要调超参数时再划validation，不能用测试窗口决定布局。

## 同步核实的实现边界

本轮pruned Left/Right都是综合前固定的实现。当前36个实例有两种方向；若要声称可配置模板比固定模板更值得，区域旋转核验已完成：[18个0°+18个180°可恢复当前几何与字节份额](../reports/TEMPLATE_BINDING_REPORT.md)。尚需制造资料确认pad/宏/曝光方向合法性，以及保留配置能力的实际需求；不要重复做区域对称检查。不能仅以“不是我们的模板”排除强基线。

B的RTL beat reservoir与C/RX3的系统整字预留不是同一合同。完整性能–面积点只能使用同一设计的执行与成本；未知面积保留未知，proxy不合并成PPA。只对有价值的候选补这个合同连接，不另起接口机制研究。

## 代码与复查

- 公共模型：`domain`、`service`；设计选择：`synthesis`；输入：`workloads`。
- 静态专用对照：`rtl/baselines/endpoint_fixed_source.sv`。
- 运行：`experiments/run_static_binding_baseline.py`；独立核对：`validation/static_binding.py`。
- 统一证据账本：`analysis/research_evidence.py`，只读已有归档，不启动性能实验。
- 本地开发 → 唯一main → Git同步服务器实验。原始trace、大构建和凭据不入Git。

```sh
python -m w2w analyze_research_evidence --output build/research_evidence
python -m w2w audit_static_binding --output build/static_binding_audit.json
```

历史逐轮建议见[NEXT_TASK_HISTORY](NEXT_TASK_HISTORY.md)及各阶段报告；不要将其中的“下一步”重新当作当前任务。整片signoff仍依赖实际PDK、DRAM宏和HB资产，当前不以新增仿真器代替。

## hn072独立复核已完成

同一注册输入在`/Projects/haoning/w2w-cohort-independent-20261008`以源码`a626eff`、4 workers完成81次回放（5038.48 s）；`ed12c69`自动收尾通过。48个原始请求重新编译、45份逻辑输入核对通过，81项均完成逐字与资源审计。本地再次审计归档，随后与eex005的81项逐条比较：执行字段完全一致，仅wall time及wire_mm浮点尾数不同。这是跨主机复现，不增加独立workload样本数。

证据在`artifacts/results/workload/cohort_replay_replica/`，身份与审计在`artifacts/provenance/cohort_replay_replica/`；`completion.json`为完成凭据，`launch.json`保留历史启动事实。两个历史PID均已退出，不再依赖后台等待或重复启动这批实验。

复查时将`replay_evidence.tar.gz`校验并解包到新的build目录，再运行：

```sh
python -m w2w audit_cohort_replica \
  --primary artifacts/results/workload/cohort_replay/flow \
  --replica <unpacked-replay> \
  --inputs artifacts/results/workload/cohort_replay/inputs \
  --output build/cohort_cross_host.json
```

详细结论沿用[同一研究的结果报告](../reports/COHORT_REPLAY_REPORT.md)，不另造重复性能表。下一步仍以上述原生供给/驻留诊断为界，不再增加matching或FIFO搜索。


## 更早的任务记录

# 当前：验证静态驻留、接口能力与请求容量的联合选择

2026-10-08：已完成[比例推导与189次有限回放](../reports/SERVICE_PROVISIONING_REPORT.md)。
在N128下，Home=4/5使窄A与宽B同为73槽分散完成；原比例为79/77槽。
供给充足时原B仍更快。完整驻留证书说明现有k3可将64套潜在Shared状态合为32套，
保留bank并行度；跨bank池化需要单独满足容量界。

下一步使用独立routing输入，冻结公式生成的候选与同等优化的Home/k2/宽k3，比较同N
完成时间及达到同目标的多项成本。共同静态owner均衡只用训练输入，测试时冻结地址映射。
重点判断增加请求entries、加宽Shared、调整比例三者的选择，不先新增pool或RTL。
本轮新比例只完成合成验证；48个真实回放只重算必要完成界。以下保留先前工作流记录。

## 真实 routing 输入闭环与服务器入口

2026-10-07 更新：已有真实输入，不再需要用合成样例代替 trace。
256 个独立 requests 已下载并逐文件核对；注册的三个 request 组、九窗口、48 次完整
读回放全部完成。[多窗口报告](../reports/PATTERNS_REPLAY_STUDY_REPORT.md)记录全部结果，
[代码分层](../CODE_STRUCTURE.md)给出输入、冻结目录、执行、审计与绘图入口。
代码在本地开发，唯一 `main` 经 Git 推送到 `HaoningJiang-space/w2w-memory`，
服务器 `/Projects/haoning/w2w` 拉取后实验；HF 默认直连，VPS 隧道停用。

接手时先复核归档，不重跑已完成的 48 个长回放。当前证据说明 k2 是强成本参考，
B 的收益依赖窗口与请求供给；下一项研究应解释服务—完整路径成本取舍。
若以后用当前 requests 选择硬件或 owner，另留独立测试输入。本轮不自动新增
FIFO/RTL/DSE，也不把读阶段完成比写成完整推理加速。

下面保留此前 ASIC 交接和当时下一步安排；“暂无 trace”只描述历史阶段。

## 历史：单 slice 物理验证与回放接口

研究主线保持：以较少共享接口硬件，让邻近 compute 使用已有闲置 DRAM 服务。
静态方向选择发生在第一次 HB 之前，不引入同 wafer 跨 reticle 转发。

## 已完成的两项

[ASIC 报告](../reports/ENDPOINT_ASIC_SLICE_REPORT.md)末节记录最终物理结果。
同 Nangate45 typical、2 ns、同 I/O 条件，source 修复后面积
21,987.294→15,318.674 μm²（−30.33%）；Configurable 虽多 357 个 hold buffer，
仍节省 6,668.620 μm²。682-FF 差不变，保留现有一套 Shared TX 核心。

Home RX 已按既有完整字合同特化，两种架构同时采用。
修复后的通用/特化 Home RX 为 9,890.944/3,815.770 μm²。
共同部件优化节省 6,075.174 μm²，不能重复记作方向复用的贡献。

Source + 特化 Home RX + 两套 Shared RX：
46,023.320→39,354.700 μm²（−14.49%）。计入 tap 后约 −14.45%。
所有正式块和通用 Home 对照均通过本轮提取后的 setup/hold、电气检查与路由器 DRC。
三个后端均通过 14 条成对轨迹，每架构 124,834 字；
通用 Home 物理网表另跑同 14 条轨迹，Home 独立周期对照为 100,004 周期。

## 下一项研究判断

用户最新要求：暂无指定 trace，先完成可验证的导入与回放 infra。
系统侧采用[逻辑读任务回放合同](../methods/READ_WORKLOAD_REPLAY.md)：固定 H/plus，复用
Home、k2 direct、k3 direct、A/B 及同布局 configurable，接入地址驻留、依赖触发、有限
outstanding/返回/RX 与任务完成时间。MoE adapter 用训练输入均衡 expert 归属，再展开
测试批的实际路由；合成验证不算真实 capture 或应用加速。它与 RTL 工作分开维护。

局部硬件验证到此收尾。系统 infra 已通过[验收](../reports/READ_WORKLOAD_INFRA_REPORT.md)，
之后接有来源的真实逻辑读任务，同时把实测局部成本
对应到完整 design 和路径，说明：

- 哪些收益来自静态伙伴/数据比例，哪些来自少复制一套 Shared TX；
- 完整路径中的 TX、RX、长线与 HB 分别计几份，避免重复计算三个 RX；
- 加入共同 RX 和长线后，sharing 相比 private/k2/direct 的收益占比还剩多少。

已有固定 H/plus 的服务结果继续作为机制证据。不因安装好 EDA 工具而自动开展
Shared RX 微优化、dual-leaf、32-bank RTL、clock/load sweep、formal、placement 或新 DSE。
只有新的真实瓶颈证据或用户的新任务才扩展这些方向。

## 证据边界与入口

本轮是独立小块的局部标准单元面积和单角时序；不代表跨 HB 端到端 timing、
wafer 长线、MCMM、功耗或真实 DRAM 工艺。保留 576 physical data lanes；
不能把 logic area 减少写成长线/HB 减少，也不把 2 ns 直接换成机制模型 TB/s。

最终 runner 源码 `6ecba5c`；source 的物理结果复用 `9cae62d`，特化 Home RX 复用
`5c7fcc0`，均核对 RTL/SDC/库/工具与 manifest 哈希链。所有原始版本保留。

服务器：`hn072@143.89.78.72`，根目录
`/Projects/haoning/w2w-memory-slice-20261007`。
主结果 `physical_6ecba5c`；通用 Home 对照 `physical_home_generic_6ecba5c`，
对照网表回放 `generic_home_replay_6ecba5c`。全部退出码 0。

[结果 JSON](../../artifacts/results/endpoint/endpoint_physical_slice.json.gz)、
[完整物理证据](../../artifacts/provenance/endpoint_physical_slice_evidence.tar.gz)、
[方法](../methods/ENDPOINT_ASIC_SLICE.md)包含源码、库、工具、输入、SPEF、ODB、网表、日志和 SHA。
旧 `5d5a958` 的未修复映射结果、`61ba73f` 的零线 RC ECO 仍为历史证据，不替代当前结果。
