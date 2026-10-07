# 静态驻留、服务能力与在途状态：固定研究协议

2026-10-08。固定 H/plus、36C+36M、32 banks/M、原有配对及 read-return 合同。
本轮从完整数据驻留推导方向覆盖，从服务/字生命周期推导新的静态比例，再用有限任务验证。
不新增跨 bank engine pool，不改变位宽、FIFO 深度、仲裁算法、RX 或 RTL。
比例变化会改变冻结的字节驻留及由其生成的加权发起配额；这两项配置变化均计入 design 身份。

## 1. 方向覆盖与 engine 粒度

对整个冻结布局的所有正字节求每 bank 的必要方向集合。一个 engine 在部署期间永久绑定
一个方向时，必要上下文数至少为该集合大小；重复模板取各实例的最大值。
即使两个方向在不同阶段才使用，也不能从此界中删除。它是方向覆盖必要界，不是总面积最小值。
同时检查整个 memory 的 Shared 方向并集，以识别现有广播单方向配置能否实现。

跨 bank pool 只给容量界，单位固定为 160 bit/slot 的一个发送器。B 的比例固定 8/13，
32 words/slot 基线需 Shared 160/13 words/slot，因此至少20个；52 words/slot 目标至少32个。
枚举 E=1,2,4,8,16,20,24,32；不把容量界当成已实现的 pool。

## 2. 从请求状态反推比例

设每 compute 的 B=32 个 Home 原生流各能提供1 word/slot，Shared 独占能力为 s，
Home 比例 lambda。当前 lH=3、lS=4 slots 的字生命周期给出必要界：

    gamma <= min(2, 1/lambda, s/(1-lambda),
                 (N/B)/(lambda*lH+(1-lambda)*lS)).

最后两项随 lambda 不减，Home 项随 lambda 减少。在 N>=B*lH 时，该松弛的最优交点为：

    lambda* = max(1/(1+s), B*lS/(N+B*(lS-lH))).

N<B*lH 时基线本身被在途容量排除，取全 Home 只给出该松弛的最大率。
这里 s 使用已有完整字执行确认的 A=1/2、B=5/8；不是任意将位宽比当作执行容量。
独立每 compute 的 issue=64 为本轮率域的上限，不比上述双 memory 界更紧。
下界不含有限条带尾部、竞争、beat相位或排队，不能直接写成达成率。

由此预先注册三个候选，不在 trace 上搜索比例：

| 候选 | 原接口 | 推导窗口 | Home 比例 |
|---|---|---:|---:|
| a_n128 | A，256/128，D1/D1 | 128 | 4/5 |
| b_n128 | B，256/160，D1/D2 | 128 | 4/5 |
| b_n160 | B，256/160，D1/D2 | 160 | 2/3 |

三者使用现有 configurable 发送状态；每个候选的 duplicated 对照保持同一新布局。
原 A/B 分别为2/3、8/13。配置 ROM/游标 proxy 随分母变化，按公共 CostModel 重算；
不得把全部硬件字段称为不变，也不校准请求 metadata 面积。

## 3. 固定对照与成功判据

Home、k2 direct、wide k3、原 A/B configurable、三个新候选，共8种配置。
每种在既有7个 synthetic_read_suite 场景和 N=128/160/192 下回放，共168次。
全部逻辑对象、地址范围、任务依赖与计算槽数保持，不为了整除新条带比例改变对象大小。
另在三个候选各自推导的 N 下执行全部7场景 duplicated 对照，共21次，总189次。

报告每个场景，不用均值隐藏 clustered/full/moving/short 的退化。成功有两个层次：
推导比例是否兑现其请求受限场景的改善；收益是否在同一目标/资源账本下值得。
同时报告更大N时的代价，以验证这不是一种普适优于原比例的配置。
既有 N 对照若在 request_window 归档中存在，则逐字段重新核对，保留强 k2。

## 4. 完成界与既有真实结果

复用 address-level window_certificate 的每任务必要读时长；新加入所有任务对同一个
native bank/出口的累计负载界。每 compute 一次只执行一个任务，因此同 compute 上各任务
必要读时长与读后计算时长之和也是总完成时间必要界；再与显式 DAG 界取最大值。
不按观测执行顺序添加依赖，不假定可预测所有任务排序。

对已归档的48个真实 routing 回放重新计算此界，核对完整 design/trace/residence/config 身份。
这一步不产生新的真实 workload 性能，不能把上界优化候选的合成结果写成真实读阶段收益。
原502次窗口研究和48次真实回放分别调用既有独立归档审计。

## 5. 产物与复现

在 eex005 干净隔离提交运行，来源、协议及输入/输出 hash 入档。
新增输出为全部189条回放、覆盖/容量/状态证书、合成对照CSV、48条真实完成界及pool必要界。
报告区分新执行、旧结果分析和解析结论；不使用当前真实窗口挑选新的伙伴或比例。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest \
  tests.test_service_provisioning tests.test_request_window tests.test_read_workload -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m w2w.experiments.run_service_provisioning --output memory_results/service_provisioning
```
