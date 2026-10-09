# 长路径反馈与返回状态的局部合同

2026-10-08。48项有限状态周期检查已完成，源码`ac08e30`，eex005执行。
它解释为什么wafer长路径的吞吐与流水存储需要一起配置；不改变cohort回放的RX3合同。

当前RTL的TX完整字FIFO、独立held beat与RX重组reservoir被抽象为占用状态。
TX至RX之间显式放入L级链路FIFO，每级ready只依赖本级时钟沿前的空位，避免跨全部
级的组合ready链。比较每级1个与2个beat槽，所有链路payload均计费。

| 位宽W、source深度D | L≥1，每级1槽 | L≥1，每级2槽 | RX payload bits |
|---|---:|---:|---:|
| 128、1 | 1/4字/槽 | 1/2字/槽 | 256 |
| 160、2 | 5/16字/槽 | 5/8字/槽 | 384 |
| 192、2 | 3/8字/槽 | 3/4字/槽 | 384 |
| 256、1 | 1/2字/槽 | 1字/槽 | 256 |

表中sink持续ready，L=1/2/4均检查。单槽ready合同在满时不能同时接收下一beat，
由此出现空泡；两槽保留了W/256的完整字速率。这不是所有单寄存链路的理论上限：
允许pop lookahead或其他反馈合同的实现必须另行检查其实际时序与状态。

RX容量为256+W−gcd(256,W)，但较小RX并不等于较小完整路径。
例如W160、D2、L1的两槽实现要计512-bit source、160-bit held、320-bit link和384-bit RX，
总payload 1,376 bits；对应W192是1,472 bits。有效位、计数、选择、驱动、线与物理修复尚未计入。
若模板保留两个Shared方向，它们的物理链路/RX不能随source复用一起删掉。

除持续ready组合，还检查停止、交替、短突发及31停/17行周期；每沿检查32-bit单位守恒，
周期首尾包含sink相位。所得48份见证保存在[原始结果](../../artifacts/results/service_principles/beat_contract.json.gz)，
[执行源码和文件哈希](../../artifacts/provenance/service_principles/manifest.json)独立保存。

这轮只证明局部占用与周期服务，尚未做payload/RTL逐周期等价、原生不可撤销返回接入或
长线时序。已有RTL继续由另一开发者维护。本结果用于确定待实现合同的完整资源边界，
不将此RX容量替换系统RX3后直接沿用旧任务时间，也不将B的面积配给C。

```sh
OPENBLAS_NUM_THREADS=1 python -m w2w probe_beat_return --output memory_results/beat_contract.json
python -m unittest tests.test_beat_return -v
```
