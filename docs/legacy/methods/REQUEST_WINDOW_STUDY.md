# 固定共享接口的请求窗口：必要界与最小可执行配置

2026-10-08 注册。延续 `FINITE_READ_STUDY.md`，只改变每 compute outstanding 字数 N。
冻结 H/plus、36C+36M、五个归档接口与两项 configurable 消融，以及布局、地址顺序、FIFO、
RX、时延、发起配额和仲裁。沿用 word/bit-budget 模型，不修改 RTL、真实路由导入或 DRAM。

## 先推导必要条件

请求从发起到交付一直占一个 outstanding。对任务中每个必需来源 p，字数为 n_p，
最小生命周期为 l_p。按执行器槽边界定义：

    l_p = request_latency + native_latency + ceil(word_bits / port_bits_p) + link_latency
    E = sum_p n_p * l_p
    N * T_read >= E

证明：每个字的占位区间至少 l_p 槽；累加区间长度等于 outstanding 随时间的离散积分，
每槽不超过 N。空队列发起、完整读后计算、无跨任务预取是当前执行合同。
周期稳态、字节比例固定时，目标率 R 必须满足 N >= ceil(R * E / sum n_p)。
这是必要界，不是充分窗口，也不把稳态率直接当有限任务加速。

默认 request/native/link=1/0/1，256-bit Home l=3，128/160-bit Shared l>=4。
B 的2496字有1536 Home、960 Shared，E=8448 word-slots，N128得T_read>=66。
Home/A/B/wide 的接口独占参考率分别为32/48/52/64 words/slot，对应必要N为96/160/176/192。
k2含private-bank计算节点，不将64 words/slot当作所有节点都可兑现的目标。

另外从每任务的必需 bank 原生字数、每路总bit/位宽、发起配额和最短管线延迟建立
与N无关的读完成下界；沿显式DAG累加读/计算/release。忽略其他任务竞争和隐含compute
串行边，只会放松下界。下界逐任务和整体对照每次回放，不能只验证胜者。

## 冻结目标与有界搜索

主场景为已有dispersed9；控制为clustered9、full36。先核对旧归档SHA及设计/驻留/trace，
在当前源码重放这三个场景的128、512配置并核对任务、事件hash、计数、stall。
每个结构自己的512完成时间是预先已知的目标，不称为无限窗口全局最优。
dispersed9另保留88、77、60槽共同deadline，分别来自已归档Private、B128和B512。

N为1..512整数。对每个目标先用必要界排除不可能N，再逐整数回放，遇首个达标即停止。
不使用二分、不假设完成时间对N单调。不依赖旧回放的偶然峰值作为充分条件。
保存所有执行过的N、原始完整回放和排除区间。与N无关的下界已超过deadline时，报告
模型内不可能；仅512未达标时，报告注册范围内未达到，不外推不可能。

每个设计最终选一个固定N，在三个场景都达到各自512参考时间：从三个已证最小值的
最大值开始逐整数检验，首个同时达标者是注册范围内的共同最小值。即使非单调也成立。
随后在全部七个原有场景用该单一N回放，保留single、moving9、straggler9和short9，
不据它们再调参数。这是预注册的机制控制，不声称统计泛化或真实应用性能。
对A/B共同最小值和dispersed9每个可达目标的最小值，回放同N configurable版本；
全部最终七场景也检查duplicated/configurable任务时间、事件hash、路由、stall等一致。

## 成本、证据与运行

请求项只计 N entries/C、36N entries/wafer 和相对128的变化。每entry的地址、tag、
返回合并、控制逻辑与实际面积未知，保留null；不冒充256-bit数据FIFO，更不与μm²相加。
原lane/TX buffer/wire、RX与pipeline等账本原样保留。投影前沿新增N这一独立维度，
仍不宣称完整系统面积或能耗。配置化与duplicated同N时，请求项相同，复用差额独立归因。

源码与本协议提交后在eex005干净隔离目录运行，单线程数值库。新增测试覆盖离散生命周期、
非完整条带、DAG、反压、时延、低credit和非单调搜索；保留原read-workload定向回归。
源提交、协议hash、旧证据hash、环境、日志和新原始回放均保存。任何守恒、身份、下界或
等价性失败立即中止，不跳过候选。结果正负均归档，不扩大接口/placement/matching搜索。

命令：

```sh
python -m unittest tests.test_request_window tests.test_read_workload -v
python -m w2w.experiments.run_request_window --output memory_results/request_window
```
