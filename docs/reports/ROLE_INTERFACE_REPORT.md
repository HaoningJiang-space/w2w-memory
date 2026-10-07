# 角色接口、静态驻留与统一模型：首轮结果

2026-10-07，实验源码 `dda731f`，eex005 独立目录
`/home/wangziheng/Video/w2w-interface-20261007`。本轮完成四个代码边界并评估
21 个冻结设计；没有改变 geometry、原生总服务或逻辑数据量。

结论：A/B 的 always-ready 优势得到正式复现，但静态比例和所需缓冲都对原生供给敏感。
当原生供给减半时，冻结的A/B会输给等宽192 D2、50/50基线；具体原因随到达时序变化。

## 代码边界与回归

- `MemoryFabricDesign / EndpointSpec / StaticLayout` 是不可变值；domain 只有标准库。
- 端点执行输出容量契约，`EndpointFixedService` 已变成兼容工厂，不再继承 LP。
- 固定字节 LP 只有一份实现；物理/端点资源矩阵集中在 `ResourceLedger`。
- 端点单测与主要契约/集成测试使用2C+2M fixture；36C用于结构回归。

历史算法保留原接口，未把不同语义的 oracle、reticle 或 bank-sharing 模型强行合并。
删除已被替代的继承/重复矩阵代码、未使用的初稿别名和导入，成本只保留一个新入口。
详见 [Design API](../DESIGN_API.md)。

eex005 上原63项测试和新增12项小系统测试全部通过；随后新增的3项wafer结构回归
及全部12项小系统测试也通过。旧64条端点轨迹、160条wafer记录、384条选型记录
重新运行/重算，与旧归档的所有非主机/提交字段一致，最大数值差 **0**。

## 相同模型里的结构比较

每结构独立冻结合法布局。k2保留边缘private bank，按实际邻居事件的超几何概率
计算9-of-36条件均值，没有套18对公式。全部硬件计数按每memory重复模板计。

| 设计 | home/shared宽度 | home比例 | 连接 | lanes | endpoint存储bit | 9/36精确均值 | 满载每C |
|---|---|---|---:|---:|---:|---:|---:|
| home direct | 256/无 | 1 | 32 | 8192 | 8192 | 1.000000 | 1.0 |
| k2 matched | 256/128 | 2/3* | 64 | 12288 | 16384 | 1.163866 | 1.0 |
| k2 wide | 256/256 | 1/2* | 64 | 16384 | 16384 | 1.327731 | 1.0 |
| k3等宽基线 | 192/192/192 | 1/2 | 96 | 18432 | 49152 | 1.385714 | 1.0 |
| k3 A | 256/128/128 | 2/3 | 96 | 16384 | 24576 | 1.385714 | 1.0 |
| k3 B | 256/160/160 | 8/13 | 96 | 18432 | 40960 | 1.482143 | 1.0 |
| k3 wide direct | 256/256/256 | 1/2 | 96 | 24576 | 8192 | 1.771429 | 1.0 |

单位TB/s/active compute。*k2比例只对可交换bank组成立，边缘未连接的bank保持全本地。
共享架构使用相同的bank/字语义；home、k2、k3配置的聚合HB分别为1、2、3 TB/s，
这些差异明确计入成本，不宣称全部资源完全相同。

在lane≤18432、endpoint存储≤49152且满载≥1的目录里，B最高。
它达到该home+两等宽shared设计族的上界1.625；对应均值上界1.482143。
此证明不覆盖任意exposure、placement或原生时序。更大lane预算的wide direct仍更快。

固定原50/50比例的消融：A接口均值只有 **1.000000**，B接口为 **1.192857**。
因此这里的收益确实需要接口与静态驻留联合改变。

## 成本结果与边界

A相对等宽基线：相同服务，lane −11.1%，endpoint存储 −50%。B：相同lane上限，
endpoint存储 −16.7%，均值 +6.96%。不过固定序列控制的显式ROM/counter计数分别为
224、352、1376 bit（基线、A、B），不能说A在每个成本维度都支配基线。

| 设计 | bank端序列化长线bit-mm | pipeline bit代理 | port端序列化长线bit-mm |
|---|---:|---:|---:|
| 等宽基线 | 355622.4 | 186240 | 474163.2 |
| A | 297497.6 | 155904 | 474163.2 |
| B | 341664.0 | 179008 | 474163.2 |

如果宽线先走到port再序列化，A/B不减少前段长线。endpoint存储没有叠加旧buffer proxy。
bank中心/Manhattan长度、2mm pipeline spacing及控制编码都只是显式代理；本地selector
线长未知，未填零当实测。以上不是PDK面积、能耗或完成布线证据。

## 新发现：原生供给会改变静态比例的优劣

三种profile均为每槽发起机会，分别是 `1`、`10`、`11110000`；后两者平均供给减半。
每条结果验证请求相位、供给相位及完整队列状态重复。这里只改变profile，保留各设计
原静态驻留及发起规则，不按场景重新摆数据。

| 设计 | always-ready均值 | alternate均值 | burst4均值 | 半供给满载 |
|---|---:|---:|---:|---:|
| 等宽192 D2 / 50:50 | 1.385714 | 0.885714 | 0.885714 | 0.5 |
| A / 2:1 | 1.385714 | 0.692857 | 0.692857 | 0.5 |
| B / 8:5 | 1.482143 | 0.741071 | 0.741071 | 0.5 |
| wide direct / 50:50 | 1.771429 | 0.885714 | 0.885714 | 0.5 |

alternate下，两路均兑现0.5，但A/B的home比例仍大于一半。更多必需字节压在home源上，
使独占服务分别降至0.75、0.8125；此时比例失配可以解释损失。

burst4下则不能只看平均供给：A的home/shared实际为0.5/0.25，B为0.5/0.375。
A的2/3比例已经平衡这两个较低的能力，其瓶颈包含共享出口丢失发起机会。
B按孤立路径能力会导出4/7的home比例候选，而非1/2。等宽192 D2在两种profile
下都兑现0.5/0.5，因而其50/50布局都可达到独占服务1。

因此下一步应将

`home比例 = 可兑现home服务 / (可兑现home服务 + 可兑现peer服务)`

作为离线设计候选生成规则。这里的服务必须由指定native profile与执行条件得出。
尚未对profile集合做鲁棒/加权布局优化；本轮敏感性已经足以否定“名义位宽比例普适最优”。

单输出诊断也复现：192-bit D1/D2在always-ready下分别0.5/0.75字每槽；alternate下
同为0.5。没有将供给不足解释成FIFO缺陷。

## 对象尾部与证据规模

对每bank 1/2/3/8/13/32/128/1024字的周期前缀做整数驻留诊断。B在13字组时恰好
实现8:5；128字组对应的独占流体上界为1.6，1024字组约1.624365。
这是整数布局的容量上界，不是有限对象完成时间仿真；不能以此替代地址级trace。

主实验：21设计×6场景×3 LP=**378 LP**；**105条周期轨迹**，另有12组供给敏感性
配置和4条单口诊断。资源共享账本最大残差 **6.28e−15**，独立配对公式最大差
**4.45e−16**。每设计通过保守瞬时HB/port/controller容量组合检查，不仅检查平均流量。
pipeline传播延时未执行建模；周期结果是特定固定序列的服务见证，不是任意流量容量区域。

下一轮优先加入原生profile驱动的离线比例选择和整数对象完成；当前不急于打开geometry。

后续第一性原理小诊断进一步验证：同为0.5的平均供给，128-bit D1在`10`下完成0.5，
在`11110000`下仅0.25；D3才恢复0.5。另验证D2突发阈值170/171-bit。
完整推导与16条轨迹见 [第一性原理分析](../theory/ROLE_INTERFACE_PRINCIPLES.md)。

## 证据与复现

- [完整结果gzip](../../artifacts/results/endpoint/role_interfaces.json.gz)
- [资源/公式验证](../../artifacts/provenance/role_interface_verification.json)
- [旧bridge与选型等价性](../../artifacts/provenance/role_interface_legacy_equivalence.json)
- [测试与归档清单](../../artifacts/provenance/role_interface_manifest.json)
- [协议](../methods/ROLE_INTERFACE_METHOD.md)

```sh
python -m unittest tests.test_design_contracts tests.test_role_interface_regression -v
python -m w2w run_role_interfaces --output memory_results/role_interfaces/results.json
python -m w2w verify_role_interfaces memory_results/role_interfaces/results.json
```

正式结果的源码号与协议哈希保留运行时值；后续说明和无行为清理提交不会改写旧证据。
