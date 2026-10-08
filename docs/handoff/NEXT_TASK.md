# 下一步 验证完整设计相对强基线的价值

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
