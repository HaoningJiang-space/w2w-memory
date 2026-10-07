# Endpoint Contract Gate：先确定一次完整读能够通过哪个出口

**方向正确，但仍不能从“存在 LIO tap / mux”直接推出任意 bank 可低成本连接多个
远距离 HB regions。** 本阶段停止 architecture DSE，选定一个公开数字接口边界，
明确服务合同和仍缺失的物理参数。与此无关的在途搜索已归档于
[NONUNIFORM_POOLING_REPORT.md](NONUNIFORM_POOLING_REPORT.md)。

## 1. 选定的公开接口：SeDRAM 的完整 128-bit RWDL

SeDRAM §2.1、Fig. 1、PDF pp.4–5：1 Gb 单元含八个独立的 128 Mb channels；各自
有 RA、CA、BNKSELb、CASWR、CASRD 和 128-bit RWDL。论文说明 RWDL 已完成数据总线
合并、属于 full-swing 数字信号；不同 channels 可以并发，HB 连接与该接口对齐。
这些证据支持把**完整 channel RWDL**作为本轮候选数字导出边界，而不是把 128 根
数据线的任意四分之一当成独立 bank。[SeDRAM 原论文](https://www.mdpi.com/2079-9292/12/5/1077)
· [出版方 PDF](https://mdpi-res.com/d_attachment/electronics/electronics-12-01077/article_deploy/electronics-12-01077.pdf)

Micron US20230048628A1、Figs.3D/3F/3G 则公开了感放／LIO 附近的引出、选择器和
transceiver 放置变体；其中还有在传统 I/O 与 WoW 路径间选择的控制。**这是结构披露，
不是本文多 HB 出口电路的制造或性能证明。** 其不同实施例也不能拼成一个已经流片的
统一架构。[原始专利](https://patents.google.com/patent/US20230048628A1/en)

公开结构与本研究新增电路必须分开。SeDRAM 的八通道独立性不证明单通道可同时打开
多个独立行；Micron 的局部 tap 也不证明所有地址都能从任一 tap 完整读出。

## 2. 一次完整 read 的路径与控制

```text
逻辑侧请求仲裁 / channel 控制
         │ RA, CA, BNKSELb, CASRD；单一请求所有权
         ▼
array → sense / column selection → 合并后的完整 RWDL[127:0]
                                      │
                         原公开设计：对应 HB → logic

                         本研究候选，尚未实现：
                                      │
                           完整字 selector / register
                           ├─ driver / FIFO 0 → HB region 0
                           └─ driver / FIFO 1 → HB region 1
```

原生阵列、感知／列选择和行状态是共同资源；新增出口不复制它们。每个被授权的 read
产生一个完整字，响应携带请求归属后送往相应出口。写入还需反向 mux、写使能与数据
归属；本阶段只推导读服务，不能把读路径示意图当作完整 memory protocol。

如果交换器只放在已跨 HB 的单个 compute reticle 内，它只服务该 reticle 可达的
接收者。要给另一 reticle 使用，仍需真实第二条跨层路径或显式 forwarding，不能
由软件重命名或 RDL 被动连线凭空获得。

128 bit 是所选公开接口的字宽。其 266 MHz 示例对应原始传输上限
128×266 MHz/8 = 4.256 GB/s/channel；这不自动等于任意访问模式的持续 service。
本项目旧模型的 1/32 TB/s/bank 是独立归一化假设，不能标成已按 SeDRAM 校准。

## 3. Contract 不仅是 lambda：还要规定字节可达性与串行位置

设原生可持续服务为 mu，单出口传输峰值 lambda=alpha*mu。以下 f_e 是**完整请求字节**，
不把部分数据位算作独立请求完成。

| Contract | 容量条件 | 需要的语义／实现条件 |
|---|---|---|
| F：固定份额 | f_e≤mu/s，sum f_e≤mu | 固定 rate partition；若还限定地址，另加地址可达集合 |
| E：弹性包络 | f_e≤lambda，sum f_e≤mu | 多出口可共同利用父服务；不等于多个 bank 独立并行 |
| M-direct：出口阶段择一 | f_e≤lambda*t_e，sum t_e≤eta，sum f_e≤mu | 窄输出发送期间占据共同服务路径，没有独立并发排空 |
| M-buffered：原生端择一、出口独立排空 | f_e≤mu*t_e，sum t_e≤eta；f_e≤lambda | 独立出口队列，原生服务按完整字轮流投递，各出口可并行发送 |

eta≤1 是可用时间比例。它可表示明确给定的切换／仲裁损失，但本轮 eta=0.9 仅作
敏感性点，不是任何工艺或 DRAM 的测量参数。真正的 eta 取决于 burst、切换序列、
buffer 深度和控制时序，不能事后随意选择以制造收益。

**重要修正：M 与 E 只在特定条件下有同一流体包络。**

- 无额外开销、lambda=mu 时，M-direct 对出口轮流服务，长期容量可以等于 E。
- 若 lambda=alpha*mu<mu，M-direct 有 sum f_e≤alpha*mu；不能仍允许 sum f_e=mu。
- M-buffered 在 eta=1、足够缓冲和可实现时间调度的长期放松下可达到 E 包络；它的
  独立 FIFO／并行发送电路有成本，也没有由该包络证明短请求延迟或有限队列不溢出。

例如 alpha=0.5、两个出口同时忙：E 总服务可为 mu，M-direct 只有 0.5mu；
M-buffered 的长期理想包络又可为 mu。**相同的 alpha，并不足以唯一确定系统能力。**

## 4. 固定份额与 striped exposure 的两处误区

固定四份不意味着 placement 一定没有价值。如果同一 compute 能访问全部四份，仍
可以合计获得 mu。F 与 E 的差别在于：只可达一个出口时，能否使用其他出口空闲的额度。
之前 partitioned=striped 的等价证明仅限均质、free-byte 服务包络，不涵盖任意固定数据。

另一方面，RWDL[127:0] 拆成四组 32-bit wires，通常首先表示同一个完整读字的四份位段，
不能直接当作四个独立地址 channel。若完整请求需要每份 beta_e 字节，则必须：

    f_e = beta_e * r,   sum beta_e = 1.

任何必需位段不可达，完整请求 r 就为 0。仅用 sum f_e=r 会错误地用可达部分替代缺失部分。
本轮用 LP 单独检查了“一份位段可达”和“四份全可达”，而非把前者计为四分之一完整访存。

## 5. 成本账本：什么能够直接计算，什么仍不知道

最保守的可讨论候选是在已合并的 full-swing 完整字后加选择／缓冲。它比直接把
模拟/小摆幅 LIO 扇出到远处数字 mux 更容易定义接口，但不是已完成的 DRAM 工艺设计。

| 项目 | 应记录的量 | 本轮状态 |
|---|---|---|
| 数据宽度 | native W；每出口 W_e；频率 nu；有效传输效率 | W=128 有公开例子；新增 W_e 是设计参数 |
| 出口吞吐 | lambda_e≤W_e*nu/8，另受协议效率限制 | 位宽只给链路上限，不证明阵列供给 |
| 数据连线 | sum_e W_e*L_e，驱动负载与 pipeline stages | 可做 bit-mm 代理；没有真实 floorplan/PDK |
| FIFO 存储 | sum_e D_e*W，加请求 tag / 状态 | 完整字 FIFO；深度不能由流体 LP 确定 |
| 控制 | 命令地址仲裁、唯一 owner、返回归属、写入反向选择 | 必须存在；门数、频率和等待代价尚未实现 |
| HB | 每 region 的 data/control pads、对准与双端带宽 | overlap 不是 pad alignment 证明 |

“多个出口共享一个 bank”在数字交换意义上是可构造的候选；“现有任意 LIO group
能免费独占整 bank”没有得到证实。alpha 也不是免费的 knob：s 个等宽出口的总配置
峰值是 s*alpha*mu；从 alpha=1/s 到 1，配置出口宽度最多相差 s 倍。

## 6. 本轮最小验证，而不是新的 wafer DSE

`endpoint_contract_probe.py` 只研究一个归一化父 bank、四个完整字节出口，保持请求／
地址类别固定。扫描 alpha∈[0.25,1] 的 31 个点、1/2/4 个活动出口，分别求 F、E、
M-direct、M-buffered 的显式时间份额 LP；M 另外检查 eta=0.9。

独立解析式（每个活动出口公共服务）为：

    F: mu/s
    E: min(alpha*mu, mu/n_active)
    M-direct: eta*alpha*mu/n_active
    M-buffered: min(alpha*mu, eta*mu/n_active).

F 的式子用于 n_active≤s。每个 LP 都保留父 bank mu 上限，并核对解析式和原始约束。
这张 phase diagram 回答的是**合同之间的服务差别**，不是 home/k2/k3 的等成本系统
排名；尚未把一种未证实的 endpoint 语义灌进整个 wafer 再宣布 architecture speedup。

要继续画有物理意义的 home/k2/k3/striped 系统前沿，首先要为每个配置补齐：完整字节
可达集合、native exporter 的 peak/sustainable service、serial stage 位置、buffer
与控制实现。不能只给所有现存 bank-port edges 乘一个 alpha 就称为已经物理校准。

## 7. 正确的下一层守恒式

对于固定驻留的字节类 a：

    sum_{(e,p) in Gamma(c,b,a)} f[c,b,a,e,p] = A[c,b,a]*r[c].

再叠加 native bank、endpoint、mux time、共享总线、两端 HB／controller 约束。
Gamma 明确哪些出口能提供该地址／完整字节；若 a 是必须拼装的 bit fraction，还要
按固定 beta 绑定到同一完成速率。仅有 sum_{b,e,p}f=r 仍可能偷偷退回 free residency。

固定这些合同与布局后仍是连续 LP；外层 configuration ILP 是后续可行路线。
当前最重要的交付是**可反驳、可实现性边界清楚的合同**，不是又一个 matching 算法。
