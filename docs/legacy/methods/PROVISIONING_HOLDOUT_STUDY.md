# 联合供给配置的独立请求验证

2026-10-08，执行前固定。沿用 service_provisioning 的解析候选，固定 H/plus、bank数量、
伙伴、位宽、深度、执行器和RX；本轮改变共同的静态expert owner，并验证已冻结的数据比例。

## 输入、训练与冻结

使用既有256-request corpus及原始manifest SHA256，不新增下载。排除先前48个计时请求；
按seed8108和request ID的SHA256在每个subject内排序，每科前8条训练，共64条。
接下来每科6条分成三个独立测试组，每组每科2条，共48条；组内按独立cohort哈希排序。
选择不读取专家选择或完成时间。此语料已做过总体活动统计，不称全新未观察过的数据集。

训练使用64条请求完整decode的layer0/39/78；三层分别学习owner。对batch1/4/16，
按固定训练请求顺序形成完整cohort，各步union得到冷读专家集合。每个batch大小等权；
训练分数为sum_b b*union_count_b，共同分母为R*S*3。对象尺寸沿用18,878,976 bytes。
用分数LPT分配，每compute最多4个专家；以训练最大负载、平方负载为序，与原modulo比较，
选训练目标较小者。所有架构共用这一owner；不使用几何、伙伴或测试活动训练owner。

三个测试组分别取layer0/decode17、layer39/decode65、layer78/decode113。
每组batch1/4/16为嵌套前缀，得到九个独立冷启动窗口。相同层的owner在所有batch间冻结。
保留全部128个expert静态对象、完整权重字节、同一请求依赖和逐字执行，不缩小权重。

## 87个执行组合

- 九窗口、共同N128：Home、k2、宽k3、原A、原B、A4/5、B4/5，共63次。
- 三个batch1窗口、共同N192：Home、k2、宽k3、原B、A4/5，共15次，用于窗口迁移控制。
- 九窗口、N128：原modulo owner的Home，共9次，检查普通静态负载均衡的影响。

全部issue64、RX深度2、request/native/link延迟1/0/1；max_slots500000、max_words80000000。
新比例只来自前轮推导，不按本轮结果修改。较宽B4/5作为宽度消融；A旧/新比例隔离配置作用。
duplicated/configurable逐字等价沿用前轮21个配对控制；本轮不重复整个硬件消融。

## 输出与判断

每窗口报告makespan、每任务等待、必要资源下界、全部原始计数、训练负载和owner控制。
以同owner/同N的Home和宽k3定义性能P=1/T；收益保留率为
(P_candidate-P_Home)/(P_wide-P_Home)。分母不为正时留空并报告原始时间，不截断负值或大于1的值。
宽k3是同一静态pair组织的足宽实现，不是任意动态全局共享上界。

成本分别保留lane、TX存储、接入线、pipeline、配置/selector及请求entries；同时给逐窗口
多资源非支配集合，不用未校准的面积权重。与Home比较用共同训练owner，不拿较差modulo
基线替代它。层/步只有三个固定点，不据此给总体置信区间。

准备阶段在hn072逐文件校验原始routing，冻结输入包；执行阶段在eex005干净隔离Git提交，
最多12个CPU workers。输入包保留selected原始ID/SHA、提取训练routing、全部spec/trace/demand。
独立审计重新计算训练分数与owner，从原始JSON重编译测试窗口，再验证每bank/route字节、
任务依赖、下界、配置身份、完整覆盖及所有输出SHA。原始大JSON留服务器。
