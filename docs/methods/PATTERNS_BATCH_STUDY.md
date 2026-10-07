# 真实路由批处理与闭环验证协议

固定数据集commit、八个MMLU科目各32个独立requests；种子按文件路径SHA排序抽样，
不按观测负载或文件最小排序。单文件≤32 MiB、总下载≤12 GB；公布超限排除和实际大小。
完成文件校验后可恢复下载，不支持部分字节断点。403不自动改主机重试。

统计：全部94层/全部decode格式校验，8个预注册层`0,13,26,39,52,65,78,93`用于统计；
完整128步，无复制或补齐。batch=1/2/4/8/16/32/64/128，四个固定request编组种子。
固定cohort是serving假设，不是观测continuous batching。
owner=e%36，另加两组固定平衡映射排列做敏感性；不训练或按测试routing优化。
八科混合与各科单独都报告，不能宣称覆盖所有模型和服务场景。

每layer/batch中distinct expert读一次完整权重，跨batch冷读。复用节省对照为
`1-distinct/(batch_tokens*top_k)`，这是冷权重字节模型，不是实测DRAM流量。
报告active compute、peak/mean需求、固定物理18对共享伙伴的一忙一闲概率、负载差和相关。
该pair来自既有k3目录，不能按新trace重配。
两个伙伴始终同忙但负载量不同仍可能有帮助，所以同时报告加权需求差。

`max(home memory bytes)/mu`与`max(pair-striped memory bytes)/mu`都是
只计memory service的完成时间下界；其比值不是endpoint加速，也不是一般性能上界。
统计间隔是request/order/mapping敏感性范围，不将token窗口当独立样本给虚假置信区间。

闭环另选前一轮已经冻结的request93、layer0、第一个decode，batch1；完整8个expert读取，
每expert18,878,976 bytes（FP8 payload+模型FP32 scales），4,719,744个32-byte字。
不缩权重、不截断专家；另外128个专家均计入该层静态驻留。
使用既有Home/k2/k3-direct/k3-buffered/k3-shared-egress五设计，固定mapping、相同请求/RX配置，
max_words=10M、max_slots=200K、最多四个独立进程。每步守恒检查及完成哈希保留；
duplicated/configurable接口需逐服务记录一致。成本按既有代理独立报告，不伪造系统PPA。
这是实际routing驱动的有限读阶段模型，不包括GEMM、KV、dispatch/combine、DRAM timing，
不能称作完整LLM推理加速。
