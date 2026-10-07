# 当前：真实 routing 输入闭环完成，回到服务与成本归因

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
