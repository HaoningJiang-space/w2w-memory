# 冻结静态映射在独立请求上的完整读回放

2026-10-08。81项已注册回放全部完成并独立核验，读取1,815,921,504个32-byte完整字。
训练侧评分改善没有普遍转化成任务改善：Home/k2九窗口均持平，C改善两个窗口，
宽k3改善四个、退化一个。各自采用冻结cohort owner后，C相对Home六窗口更快，
一个相同，两个慢2槽。有限共享仍有价值，但并非统一加速。

更有用的下一步依据是：81项执行距离各自的必要资源下界最多11槽、相对最多0.0173%。
在当前合同与冻结驻留下，再微调仲裁很难带来明显收益；需要改变必需工作量的分配、
实际容量或请求/返回合同。后续应从DRAM真正独立的服务域构造这些选择。

## 比较与输入

[注册协议](../methods/COHORT_REPLAY_STUDY.md)在本轮routing读取与执行前冻结。
复用既有64请求训练探针的四份owner，各自执行相同8轮、每轮256个候选交换后冻结；
本轮不重新训练、不按测试窗口选布局。伙伴、位宽、比例及每compute常驻专家数不变。

从既有256请求语料排除旧计时48、训练64和上一轮测试48，按ID哈希选择剩余48请求。
三组各16请求，layer0分别取decode step17/65/113；各组的batch1/4/16嵌套，共九个窗口。
三组distinct专家数分别为(8,32,78)、(8,31,67)、(8,29,81)。所有128个专家常驻，
每个被选中的专家完整读取18,878,976 bytes；没有缩小权重或抽样字。

Home、k2、wide、C各比较边际LPT与自己的cohort owner，共72次；C duplicated再执行
九次完全相同的cohort输入，共81次。Home也有同等训练机会，但本轮没有额外执行新的
modulo Home，不能称作击败所有合理Home布局。之前语料的总体characterization已存在，
这些是新请求上的冻结评价，不称全新未观察的数据集。

固定H/plus、36C+36M、32机制bank/M、1 TB/s原生slot预算/M、N192、RX3、
request/native/link=1/0/1槽、持续ready。C是256/192/192、D1/D2、λ=4/7。
本轮保持整字RX预留合同以隔离映射；不加入HBM2、beat reservoir或新的RTL。

## 同一硬件上的映射收益

| 结构 | 更快 / 相同 / 更慢 | 九窗口几何平均速度比 | 最大改善与退化 |
|---|---|---:|---|
| Home | 0 / 9 / 0 | 1.0000 | 均不变 |
| k2 | 0 / 9 / 0 | 1.0000 | 均不变 |
| 宽k3 | 4 / 4 / 1 | 1.1493 | 两个窗口时间约减半；一个增加33.32% |
| C | 2 / 7 / 0 | 1.1324 | 两个窗口时间减少42.85% |

宽k3的四次改善包含G3/B4仅3槽、0.0108%的变化；不把它与时间减半同等描述。
其G2/B4从27,661变为36,879槽，完整保留这一退化。
几何平均仅汇总这九个注册窗口，嵌套batch具有相关性；不是服务请求加权的LLM速度比，
也没有以训练评分或平均带宽倒数代替实测完成时间。

![同一硬件下的完整读完成时间变化](../../artifacts/figures/cohort_replay/cohort.svg)

[PDF](../../artifacts/figures/cohort_replay/cohort.pdf)；图中G1/G2/G3对应case c0/c1/c2，
0.0108%的小改善在一位小数显示中为+0.0%。[全部36行成对数据](../../artifacts/results/workload/cohort_replay/analysis/paired_times.csv)。

## 各自冻结cohort布局后的结构比较

下表单位slot，直接比较同一逻辑任务的最后完成时间。每个结构使用自己的训练owner，
因此这是组织与fabric共同作用，不能全部归因于某个接口。

| 窗口 | Home | k2 | 宽k3 | C | Home/C速度比 |
|---|---:|---:|---:|---:|---:|
| G1/B1 | 18,439 | 18,439 | 9,221 | 10,538 | 1.7498 |
| G1/B4 | 36,878 | 36,878 | 27,660 | 28,977 | 1.2727 |
| G1/B16 | 55,317 | 55,317 | 55,318 | 55,319 | 0.99996 |
| G2/B1 | 18,439 | 18,439 | 18,440 | 18,439 | 1.0000 |
| G2/B4 | 36,878 | 36,878 | 36,879 | 28,977 | 1.2727 |
| G2/B16 | 55,317 | 55,317 | 55,318 | 55,319 | 0.99996 |
| G3/B1 | 18,439 | 18,439 | 9,221 | 10,538 | 1.7498 |
| G3/B4 | 55,317 | 55,317 | 27,660 | 31,614 | 1.7498 |
| G3/B16 | 73,756 | 73,756 | 55,320 | 65,857 | 1.1199 |

宽k3不是全局pooling上界。在其有正收益的五个窗口，按速度增量计算，C保留约
35.99%–81.82%；G2/B4反而是C更快，宽k3相对Home无正增量，不定义“保留比例”。
不能把旧五窗口81.82%–83.32%的结果不加检验地搬到这组新请求。

81项结果与独立必要下界相差0–11槽，最大相对差0.017258%。例如G3/B16的C为
65,857槽，聚合资源下界65,846槽。该结论只适用于当前slot与请求合同；原生命令模型
会改变容量集合，不能把这些数当实际DRAM下界。

## 同服务的实现消融与制造计数

九组C duplicated/configurable的任务、路径、stall、delivery hash、bank字节和峰值在途
完全一致。下面保留每memory重复模板计数；它们来自同一冻结设计，不是面积估计。

| 结构 | Lane bits | TX payload代理 bits | RX3 payload代理 bits | 接入wire bit-mm | 流水寄存代理 bits |
|---|---:|---:|---:|---:|---:|
| Home | 8,192 | 8,192 | 24,576 | 120,832.0 | 63,488 |
| k2 | 16,384 | 8,192 | 49,152 | 241,561.6 | 126,976 |
| 宽k3 | 24,576 | 8,192 | 73,728 | 474,163.2 | 248,320 |
| C configurable | 20,480 | 24,576 | 73,728 | 385,830.4 | 202,112 |
| C duplicated | 20,480 | 40,960 | 73,728 | 385,830.4 | 202,112 |

RX代理沿用已有账本公式bank-port连接数×3×256，计入制造方向；不是实际RTL的
beat-reservoir面积。所有设计统一RX3是本轮映射隔离合同，不声称这是每种direct基线的
最小RX实现。控制、选择器和配置等分项仍在原始CostModel记录；未知选择器线长保留null。
全局N192需要请求状态，但本表未标定其物理面积。流水按2mm一级代理，未做长线时序。

C相对宽k3少16.67% lane和18.63% wire，同时增加TX状态；同一C的方向复用减少TX
payload，却保留全部物理lane、wire及RX。不得用B的局部P&R替代C的完整成本。
另一开发者的[固定裁剪强基线](../RESEARCH_STATUS.md)及[条件旋转构造](TEMPLATE_BINDING_REPORT.md)
继续保留，不能把未裁剪duplicated称为最佳专用实现。

## 对下一版设计的判断

目前值得推进的是**以真实原生出口域为粒度，联合选择静态字节比例和请求/返回容量**。
本轮固定合同下已接近资源下界，训练owner的改善又不普遍；继续增加FIFO变体不足以
解决这些现象。需要先问哪些DRAM资源真正并行、哪些已共享总线，再配置出口硬件。

同步完成的[原生比例诊断](NATIVE_MATCHED_RESIDENCY_REPORT.md)提供了一个具体例子：
同一B接口与HBM2组织，仅由8/13改为1/2，单个完整对象读时间减少17.44%。
它表明接口宽度不能单独决定驻留比例。下一次有意义的原生实验应固定同一profile，
选择多对象竞争，分别记录原生服务域工作量、等待与返回预留占用；不复用本轮测试来重调owner。

Wafer侧继续明确模板方向、允许的实例朝向和长线/反馈状态；DRAM侧保留实际独立
并行度与不可撤销返回容量。完整推导见[第一性约束与具体设计顺序](../methods/WAFER_DRAM_SERVICE_PRINCIPLES.md)。

## 复现与审计范围

- 输入准备和81次执行源码`0e66ff7ce0d80d1ed8d98f2e6ab436128d0d13aa`，干净源码；
  原始routing在hn072重编译，12-worker回放在eex005运行1,922.74 s。
- 输入独立核对45份trace、48份原始request；结果核对81记录及九组同服务消融。
  原始routing的重编译在准备记录中，结果审计本身使用归档提取数据，不重复声称读取了raw。
- 本轮53项模型/输入/审计测试通过；4项仓库入口测试另行通过，共57项。
  没有重新声明旧全套或新增RTL/P&R通过。
- [原始81项与逐字摘要](../../artifacts/results/workload/cohort_replay/flow/summary.json)、
  [配对统计](../../artifacts/results/workload/cohort_replay/analysis/analysis.json)、
  [独立核验](../../artifacts/provenance/cohort_replay/cohort_audit.json)、
  [溯源与文件哈希](../../artifacts/provenance/cohort_replay/manifest.json)。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m w2w audit_cohort_replay \
  --inputs artifacts/results/workload/cohort_replay/inputs \
  --source artifacts/results/workload/cohort_replay/flow --output build/cohort_audit.json
python -m w2w finalize_cohort_replay \
  --inputs artifacts/results/workload/cohort_replay/inputs \
  --source artifacts/results/workload/cohort_replay/flow --output build/cohort_finalized
```

两条命令核对/汇总归档，不重新训练或长回放。以上性能表来自eex005批次；hn072独立复现如下，不拼接为更多测试样本。

## 跨主机复现已完成

hn072以`a626eff`、Python 3.10.12、4 workers执行相同81项，耗时5038.48 s；
eex005原执行为`0e66ff7`、Python 3.13.13、12 workers。两个提交之间的service、domain、
本实验workload/设计/runner代码无差异。服务模型未因跨主机复核而修改。

- hn072重新读取48份原始routing，核对45份逻辑输入；该raw核验与后续结果审计分开记录。
- hn072完整交付1,815,921,504个32-byte字，服务器自动审计及下载后的本地独立审计均通过。
- 两主机81项的完成时间、task/route、stall、交付hash、bank工作量、峰值在途和必要资源界全部精确一致。
- 唯一行字段差异为实际运行耗时和`cost.wire_mm`的浮点累加尾数；后者按1e-12相对/绝对容差核对，不把成本字段整体忽略。
- 新核对器的篡改拒绝测试、原cohort测试和仓库入口测试共11项通过。

[跨主机核对](../../artifacts/provenance/cohort_replay_replica/cross_host_check.json) ·
[完成与哈希记录](../../artifacts/provenance/cohort_replay_replica/completion.json) ·
[独立执行原始证据包](../../artifacts/results/workload/cohort_replay_replica/replay_evidence.tar.gz)。

这提高了执行结果的可复现性，**没有增加workload覆盖或证明DRAM实现正确**。
九窗口仍为同一套冻结研究；C/Home几何平均速度比约1.2874，宽k3/Home约1.3430，k2/Home为1。
这些汇总不是完整LLM速度比，更不能与不同合同的B面积拼接成端到端Pareto点。
