# 下一步 验证完整设计相对强基线的价值

研究主线是有限成本下的wafer-scale memory service provisioning。当前首先读[统一证据与新强基线](../RESEARCH_STATUS.md)。DRAM接口验证已经归档，不再作为主研究任务。

## 已完成 不重复开发

- 真实routing导入、冻结读任务、166次独立请求回放与逐字审计。
- bank-local configurable source及局部RTL/P&R；不是跨bank engine pool。
- 本轮新增六项同库映射、28项配对mapped回放：固定专用source更小，可配置source以约4%面积开销保留部署方向选择。
- cohort owner有训练侧有限交换探针；新81次回放协议与准备/运行/审计代码已由另一开发者提交，尚未在此核验其完成结果。
- 公开HBM2后端与8次完整对象探针保留为可选验证，不用于当前性能排名。

## 当前唯一主要实验

固定现有几何、原生服务、HB/位宽和N预算，比较Home、k2、B及wide参考，在同等cohort训练预算下选择并冻结owner/数据组织。保留modulo、边际LPT、共同owner对照。注册测试requests、layer和step之前排除已有训练/选型/计时集合；已经看过的窗口只用于诊断。

输出每个窗口的完成时间、负例和成本分项，而不是只报同owner Home上的平均speedup。wide不是full pooling；固定专用、未裁剪duplicated、configurable也不是同一服务范围。若不改变硬件而改善owner，必须单列其贡献。

已有[冻结cohort回放协议](../methods/COHORT_REPLAY_STUDY.md)及`prepare_cohort_replay`、`run_cohort_replay`、`validation/cohort_replay.py`，优先完成并审计这批注册的81次回放，不重复另建测试集。该批是Home/k2/wide/C与LPT对照，不能改称B实验或等同完整成本比较。

当前已有`synthesis/cohort_placement.py`、`theory/cohort_service.py`和训练探针，先复用，不增加新优化框架。训练、冻结、测试分开；需要调超参数时再划validation，不能用测试窗口决定布局。

## 同步核实的实现边界

本轮pruned Left/Right都是综合前固定的实现。当前36个实例有两种方向；若要声称可配置模板比固定模板更值得，必须检查固定模板的合法旋转/布线复用，以及保留配置能力的实际需求。不能仅以“不是我们的模板”排除强基线。

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
