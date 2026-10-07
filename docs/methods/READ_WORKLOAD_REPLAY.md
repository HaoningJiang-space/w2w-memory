# 固定 H/plus 的逻辑读任务回放合同

2026-10-07；本轮只补系统侧 infra，RTL/ASIC 修复由另一开发者负责。

研究问题是：静态数据组织是否同时创造运行时服务机会和实现时硬件复用机会。
本轮的交付是可复核的请求、地址、依赖和成本接口；合成验证不是应用加速结果。
旧架构竞争中的 random9/clustered9、周期满载保底和 LP 结果保持原合同。

## 冻结对照与证据范围

从 `architecture_competition.json.gz` 重建五个已有候选：Home direct、k2 方向 2/3
full-width direct、k3 方向 2/3 full-width direct、k3 A、k3 B。A/B 各增加同布局、
同位宽的 configurable shared-egress 消融，共七项。重建必须匹配原布局哈希和 CostModel。
不重新优化 placement、matching、方向、比例或位宽，不按测试活动样本选择布局。

结构比较共用同一逻辑对象、compute 归属、任务 DAG、时序和 credit 假设；各自按已有合法
静态布局编译地址。实现比较额外要求 residence、逐任务时间、逐路计数、停顿、交付事件
哈希完全相等。这里只检查系统模型中的同服务；RTL 逐 bit/逐周期等价由其独立证据负责。

这些是预注册代表点，不能把其中最优称为新的全设计族最优。新 workload 下的有限任务
执行不继承旧周期活动模型的满载每 C 1 TB/s 保证。请求供给、有限尾部、同步和 credit
均可能使它更慢；真实任务结果必须显示这种代价。

## 逻辑输入与真实捕获边界

`w2w.read-trace.v1` JSON 顶层含 `schema, evidence, source, word_bytes, objects, tasks`：

```json
{
  "schema": "w2w.read-trace.v1",
  "evidence": "synthetic",
  "source": "minimal documented example",
  "word_bytes": 32,
  "objects": [{"id": "expert0", "size_bytes": 416, "compute": 0}],
  "tasks": [{"id": "read0", "compute": 0,
             "reads": [{"object": "expert0", "offset_bytes": 0, "size_bytes": 416}],
             "dependencies": [], "release_slot": 0, "compute_slots": 0}]
}
```

所有地址和长度为完整 32-byte 字；v1 拒绝未对齐输入，不能默默丢尾字节。允许同对象
不同范围、重复读取、释放时刻、读后计算延迟及依赖。`compute=null` 的无读任务可作 join。
对象有唯一静态 compute 所有者，v1 不处理多消费者对象复制或运行时迁移。
每 compute 同时运行一个任务；多个就绪任务以 ID 排序。内存读取完成后执行指定计算延迟，
其后释放 compute 并触发后继。读与计算不重叠，是显式可替换的初版任务合同。

`w2w.moe-routes.v1` 用于导入**单层**、逐批逐 token 的专家选择：

```json
{
  "schema": "w2w.moe-routes.v1", "evidence": "captured",
  "source": "model revision / capture command / dataset revision / source trace SHA",
  "split": "test", "layer": "layer_0",
  "experts": [{"id": "e0", "size_bytes": 416}, {"id": "e1", "size_bytes": 416}],
  "batches": [{"id": "test_batch_0", "selections": [["e0", "e1"], ["e0", "e1"]]}]
}
```

必须另给不重叠的 `split=train` 输入，expert 对象及 layer 相同。由训练批中实际出现的
专家累计冷读字节，以 LPT 贪心平衡 compute 负载，resident bytes 用作平局控制；所有架构
共用该归属，Home 因而有同等的静态负载均衡机会。它不是全局最优分配，也没有缓存优化。
原始输入、训练/测试哈希和最终归属均进入输出。批 ID 交叉检查能捕获直接泄漏，不能替代
上游数据集划分审计。

每批一个专家只读取一次完整权重，允许批内 token 复用；批间无缓存。每批结束后才发起
下一批，join 由实际完成触发。该 adapter 不产生 expert GEMM、dispatch、combine 或整模型
时间；路由是 captured 也不意味着任务时间是 measured。真实执行语义更细时应导入完整
read-trace DAG。合成 demo 明确标为 synthetic，没有下载模型、运行推理或伪造 capture。

## 冻结驻留与阶段字节

将已有每 compute 的 bank 份额转换为有界有理数周期，以确定性的平滑加权轮转编译
完整字序列。周期上限 65,536；无法精确匹配时拒绝，不近似抹去稀有来源。对象从自身
word 0 开始条带，所有对象的实际 resident bytes 都计入 bank 容量，包含此次未被读取者。
不同对象获得不重叠 bank 内地址，无复制。布局内存占用随对象数和条带周期增长，
不会先物化数十亿个 weight word。

每个实际读地址解析为 `(memory, bank, bank_word_address, physical_port, HB_edge)`。
合法路径和静态 shared direction 由原 Design/CandidateEvaluator 校验。冻结哈希绑定
对象、几何、exposure、地址算法和周期；它不含 duplicated/configurable 的状态复制差异。
完整 design hash 则包含 endpoint、所有静态方向及份额。

结果从每个 task 的实际地址分别计算 `bank_bytes` 与 `memory_byte_fractions`。冻结的是
地址映射，部分对象读取不被强迫维持 8:5。`read_trace` 不同阶段可以有不同 A。

## 有限请求、原生返回及 RX

时间单位是原生 bank slot，`slot_ns = word_bits / (8000 * bank_bw_TB_s)`。
当前 H/plus 为 1.024 ns；这不沿用 ASIC 的 2 ns 时钟，也不声称完成物理频率校准。

默认配置为：请求延迟 1 slot、native 返回延迟 0、link 延迟 1、每 C 每 slot 最多
64 个请求字、每 C 最多 128 个 outstanding 字、每 bank/output RX 深度 2、RX always-ready。
默认 native=0 与已注册 always-ready 机制模型对应；非零 native 延迟用于有限 credit
敏感性，**不是 DRAM command/timing 校准**。最多 100,000 slots / 10,000,000 logical words，
超限报错，不隐式抽样或返回“成功”的部分结果。

每槽严格按以下顺序执行：

1. RX 收齐且 link 延迟结束的完整字在槽边界交付，归还 outstanding credit；推进任务 DAG。
2. 新任务按发起上限和 outstanding credit 发送地址，请求延迟后才能进入 bank 仲裁。
3. 每 bank 至多接受一个 native word；按冻结的比例轮转，跳过尚无请求的方向，被选方向
   无 source 空间则阻塞。`NativeProfile.ready` 限制接收机会。被接受的不可撤销返回立即
   预留 source 槽，native 延迟内仍占 credit，不能用隐藏的无限返回队列吸收。
4. 各合法输出按实际位宽发送，支持跨字 beat 与有限尾部；字首位发送前预留一个 RX 槽，
   最后一位后经过 link 延迟，在下一槽边界或以后完成。RX readiness 可延迟消费并反压 TX。

非零 native 延迟占 source 槽会保守地压低浅队列/direct 服务；这是明确的 reservation
协议成本，不能拿该敏感性证明真实 DRAM 上 buffered 获胜。v1 尚无独立 DRAM command
pipeline 或时序模型。输入 request_words_per_compute_slot 是显式控制路径服务假设，
对应电路未实现；地址/标识位没有冒充免费数据 lane。

所有常驻输出的瞬时峰值仍须通过公共 ledger 的 memory port、HB、compute port 和
controller 组合证书；失败的设计被拒绝，不暗用无限下游。未模拟长线逐级传播，固定 link
延迟只是模型输入。每槽检查请求数、完整字、发送 bit、outstanding 与 RX 守恒；结束
必须清空所有必要字节。发送模型使用 bit budget，不执行数据值、RTL held-beat 或电气延迟。

## 完成与成本输出

输出包括 task start/read-done/finish、compute 排队、每任务 memory 等待、全 DAG makespan、
有效读 bytes/time、逐 bank/方向利用、source/RX 峰值和停顿。等待总和单独标为求和量，
不是墙钟时间；join 已包含最后一个必要操作。不能取平均带宽的倒数替代任务时间。

每 design 附公共 CostModel 完整分项；物理方向、lane、HB 和长线仍按制造模板收费。
模型新增加的 RX payload allocation 按所有制造输出收费，单列每 C outstanding 与请求
发起假设；metadata、控制、request path、物理支持面积尚无校准，保留 null。
不把这些 bits 加成系统面积，不拼接修复前 35.6%/16.3% 到新设计。

`--hardware-evidence` 可输入带 `design_sha256, artifact, artifact_sha256, source_commit,
scope, timing_closed, measurements` 的记录数组。artifact 相对该 JSON 所在目录解析，
校验原始文件 SHA；哈希必须属于本次完整 design。该接口仅绑定单独证据，不认证数值、
时钟兼容或完整成本。`hardware_evidence_complete=false` 保留到完整范围另行审计。

## 运行与验收

仅在 eex005 干净隔离源码运行；沿用现有 venv，不使用 RTL 开发者的工作目录。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m unittest tests.test_read_workload tests.test_design_contracts tests.test_role_interface_regression tests.test_repository_layout -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m w2w run_read_workload --demo --output memory_results/read_workload/results.json
# 真实路由必须由外部捕获并保留来源；下列文件只是用户输入位置示例。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/wangziheng/Video/w2w-memory/.venv/bin/python \
  -m w2w run_read_workload --training-routes train.json --routes test.json \
  --output memory_results/read_workload/captured.json
```

验收包含独立解析小例、必需远端字节、160-bit 跨字尾部、地址唯一性、容量、变化的 A、
依赖触发、有限 credit/RX/原生停顿、非法输入/超限拒绝及两组完整实现消融。
下一步接有来源的 capture 和实际等待，随后只按观察到的瓶颈改变一个架构要素。
