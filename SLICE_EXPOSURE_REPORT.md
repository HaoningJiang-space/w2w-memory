# Striped exposure 最小核验：先确定 LIO 端点的服务语义

**把模型下沉到 bank slice/LIO endpoint 有意义，但“更细粒度”本身尚不能推出 pooling 收益。**
eex005 已完成 108 次容量包络计算；在每个 bank 保留共享总服务上限的条件下，结果明确
区分了两种端点假设。[模型与推导](SLICE_EXPOSURE_METHOD.md) · [完整结果](slice_exposure_results.json)。

这不是固定数据布局实验。最大流允许自由选择从哪些 bank/slices 取字节；没有验证地址
可达性、word assembly、独立行访问或 DRAM 实现。它先回答“接口容量模型是否真的不同”。

## 结果

每 M 32 banks，每 bank 4 slices；bank 服务 μ=1/32 TB/s。所有模式共享同样的
36C+36M、每 M 1 TB/s、每 C/M 4 TB/s HB、每 C 4 TB/s controller。
同一端点假设下 A/B/C 只有接线不同；跨端点假设的原生接口能力并不相同，不能称为等成本。

**同一个内部 compute 单活动，单位 TB/s：**

| Placement | A partitioned，两种 λ 都一样 | B striped，λ=μ/4 | B striped，λ=μ | C free pooling，两种 λ 都一样 |
|---|---:|---:|---:|---:|
| Aligned | 1 | 1 | 1 | 1 |
| X-shift | 1 | 1 | 2 | 2 |
| XY-shift | 1 | 1 | 4 | 4 |

**全部 compute 活动，总服务 TB/s：**

| Placement | A / B固定份额 | B可共享 bank 服务 / C |
|---|---:|---:|
| Aligned | 36 | 36 |
| X-shift | 33 | 36 |
| XY-shift | 30.25 | 36 |

四个固定随机 seeds（9000–9003）的 25% 活动场景也全部满足相同的等价关系。
这里没有搜索 winner，未用这些结果调整结构或参数。

## 推论

如果每个 slice 的服务严格上限是 μ/4，那么 A 的“8 banks × μ”和 B 的
“32 banks × μ/4”给一个 port 的都是 1/4 TB/s。父 bank 的 μ 约束又等于四个
slice 上限之和，所以在这个均质、自由取数模型中，A/B 可以收缩成同一张容量图。
这说明**固定切分内部带宽后再交错，并不会自动回收闲置份额**。

如果每个 slice 可以使用 μ，但四组总和仍受父 bank 的 μ 约束，那么 B 每个 port
都能访问全部 banks 的服务能力；其容量包络恰好等价于本模型的 C。这次没有把四个
slice 算成四颗独立 bank，总 DRAM 服务始终不超过 36 TB/s。

第二行模型不是公开技术已经证明的能力。它把真正的问题指出来了：
**某个 LIO group 是否能独占 bank 的服务额度，还是只能提供固定部分带宽？**
同时必须确定 group 是独立地址片段，还是一次完整读出中的部分位段。
如果完整请求需要多组拼接，仅一组可达不能算完成一次访存。

因此，这不是否定 Striped Bank Exposure；它说明需要把这个 idea 从“分散连线”
进一步落到“原生端点服务 + 共享 bank 约束 + 地址/数据组装语义”。
Micron 披露支持 tap、mux 和接口位置的自由度，但没有直接给出上述 λ 参数或任意
group 独立完成请求的保证。[原始披露，Figs. 3C–3G](https://patents.google.com/patent/US20230048628A1/en)。

## 下一步只问一个问题

选一个具体公开结构或阵列宏，追踪一次完整读请求：经过哪些 LIO groups，每个组的
峰值输出和共享瓶颈在哪里。由此确定 λ，以及这些组能否代表独立地址资源。
这个端点 contract 确定后，再做相同静态地址布局下的 A/B 比较。
本轮没有启动新的 DSE、设计 mux/crossbar 或扩大 workload 范围。

## 复核

实验提交 `75bc4646f9a9f8a866b2aa65890b15ed4a959b8a`，eex005 工作树干净；
运行约 22.8 秒。新增两项测试在本地和服务器均通过；旧阶段的 31 项测试记录保留。
所有 108 次计算逐边检查整数流容量、逐节点检查流守恒，并核对三组等价关系。

原始结果：eex005 `memory_results/eex005_slice_75bc464/results.json`；
相同文件已下载为本仓库 `slice_exposure_results.json`，SHA256：
`6a9781d0b510c6242866f0228a28a6d7159d7cf4f2aa82d27c1489c3de0e3888`。
