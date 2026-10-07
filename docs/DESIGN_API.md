# 设计对象、端点契约与资源账本

本轮固定四个边界，没有改写历史 matching、placement、DSE 算法。

```text
domain: MemoryFabricDesign / Geometry / Exposure / EndpointSpec / StaticLayout
             ↓                            ↓
      service.adapters              endpoints execution
             ↓                            ↓
      service.resources  ←──────── EndpointEnvelope
             ↓
        service.solver  ─────→ service.evaluator
             ↓                       ↓
      ledger.load/audit       synthesis / experiments
```

`domain/` 仅使用标准库不可变值；嵌套数组转为 tuple，没有 NumPy、SciPy、Shapely、
NetworkX 或文件 IO。一个 design 包含冻结几何路线、重复 exposure、端点/native profile、
静态字节比例。改变参数使用 `dataclasses.replace` 产生新设计。

| 职责 | 唯一的新入口 |
|---|---|
| 不可变设计 | `w2w.domain.MemoryFabricDesign` |
| 完整字周期执行 | `w2w.endpoints.role_execution.execute_periodic` |
| 端点合同值 | `w2w.domain.EndpointEnvelope` |
| 物理资源行与端点行 | `w2w.service.resources` |
| 固定字节 LP | `w2w.service.solver.FixedService` |
| Design + workload 求解 | `w2w.service.adapters.solve_service` |
| 局部周期服务组合 | `w2w.service.evaluator.CandidateEvaluator` |
| 分阶段硬件计数 | `w2w.service.cost.CostModel.evaluate` |
| 独立模板容量界 | `w2w.theory.interfaces.pair_lane_bound` |

`ResourceLedger` 统一构造 bank、bank-output、HB、memory-port、compute-port 和端点
占用行；新 Design API 显式列 controller 行。旧 API 保留 controller 的变量上界，
避免仅因重复行改变历史 LP 对偶证据。求解器与 `audit_rates` 使用同一个 ledger；
配对解析式、手算小系统与整数成本计数仍作为独立 oracle。

端点模块的执行逻辑不导入 service。历史 `EndpointFixedService(...)` 导入通过懒加载
兼容工厂生成 envelope，再调用同一个 `FixedService`；已经删除继承实现和重复矩阵拼装。
旧 `guaranteed_service_exchange.FixedService` 是兼容导出，不是第二个 solver。

新 synthesis 只构造设计、枚举与选择，不读取 solver 矩阵或 FIFO 内部状态。
构造阶段暂复用旧公开几何/布局工厂，再复制成冻结 Design。其余历史算法仍通过旧
API 工作；`bank_sharing`、`matching_placement`、oracle relaxation 的不同语义尚未
整体迁移，不宣称全仓库已经只剩一种数学模型。旧 `ExposureFabric.cost()` 保留历史
结果口径；本轮所有新候选统一经过 `CostModel`。

测试分工：`tests/test_design_contracts.py` 包含纯端点 unit、envelope/ledger contract、
2C+2M integration；fixture 在 `tests/fixtures/tiny_fabric.py`，不调用36C几何。
现有36C相关测试和旧64轨迹/160回放保留为 regression。新版验证器读取保存结果，
使用共享 ledger 检查资源，再用独立 pair 公式检查结果；不复制资源公式。

当前 `CandidateEvaluator` 仅支持唯一物理路径、每 bank 最多两个固定所有者及能通过
保守瞬时端口容量证书的设计。通用多路径或共享端口拥塞需要独立实现，不能通过
修改 design 名字绕过这些条件。

Configurable Shared Egress 使用 `EndpointSpec.shared_fifo_ports` 指定共用存储的物理方向，
`MemoryFabricDesign.shared_directions` 冻结每 memory 的方向。构造器核对完整布局，执行器
只分配一份 shared queue，envelope 关闭未选方向的服务容量，成本仍保留其物理线路。
该类型当前限于 bank-local 等宽/等深 shared FIFO，不能随 activity set 切换配置。
